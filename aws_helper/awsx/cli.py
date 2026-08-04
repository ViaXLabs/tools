from __future__ import annotations
import os as _os
import sys as _sys

# Vendor bootstrap: if a sibling vendor/ dir exists (unpacked boto3/click/etc,
# built by scripts/build_offline_bundle.sh), put it on sys.path BEFORE
# importing anything third-party. This lets awsx run on a bastion with no
# internet access and no `pip install`, straight from a copied directory:
# `python3 -m awsx.cli ...`.
_here = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_vendor = _os.path.join(_here, "vendor")
if _os.path.isdir(_vendor) and _vendor not in _sys.path:
    _sys.path.insert(0, _vendor)

import json
import socket
import getpass
import click

# Import recipes package to trigger auto-registration of all recipes
from awsx import recipes  # noqa: F401
from awsx.registry import all_recipes, groups
from awsx.aws import base_session, get_caller_identity
from awsx import mode
from awsx import audit


def _json_default(obj):
    # Fallback for datetimes etc. that slip through un-serialized
    return str(obj)


def _make_command(recipe):
    @click.pass_context
    def _cmd(ctx, **kwargs):
        if recipe.mutating and mode.is_readonly():
            raise click.ClickException(
                f"'{recipe.group}.{recipe.name}' can mutate resources, but this is a "
                f"read-only awsx session (AWSX_READONLY set, or running as awsx-ro). Refusing."
            )

        session = base_session(ctx.obj["profile"])
        # Belt-and-suspenders: readonly mode always forces dry_run=True too,
        # even though the check above should already stop mutating recipes
        # from getting this far.
        effective_dry_run = ctx.obj["dry_run"] or mode.is_readonly()

        audit.log_invocation(
            session, f"{recipe.group}.{recipe.name}", ctx.obj["region"], effective_dry_run, kwargs
        )

        result = recipe.func(
            session,
            ctx.obj["region"],
            effective_dry_run,
            **kwargs,
        )
        if ctx.obj["pretty"]:
            click.echo(json.dumps(result, indent=2, default=_json_default))
        else:
            click.echo(json.dumps(result, default=_json_default))

    _cmd.__name__ = recipe.name.replace("-", "_")
    help_text = recipe.summary
    if recipe.mutating:
        help_text += "  [mutating: blocked in read-only mode]"
    cmd = click.Command(
        name=recipe.name,
        callback=_cmd,
        params=list(recipe.params),
        help=help_text,
    )
    return cmd


@click.group()
@click.option("--profile", default=None,
              help="AWS named profile to use. Leave unset (recommended on a bastion) to use "
                   "whatever ambient credentials the logged-in user already has: their assumed "
                   "role, SSO session, env vars, or instance profile - never a profile baked "
                   "into awsx itself.")
@click.option("--region", default=None, help="AWS region (defaults to profile/env default)")
@click.option("--execute", "execute_", is_flag=True, default=False,
              help="Actually perform mutating actions (default is dry-run / read-only preview)")
@click.option("--pretty/--compact", default=True, help="Pretty-print JSON output (default) vs compact (for piping to jq)")
@click.pass_context
def main(ctx, profile, region, execute_, pretty):
    """awsx - extensible AWS helper for operations beyond the standard CLI.

    Every recipe is READ-ONLY / DRY-RUN by default. Pass --execute to allow
    a recipe to actually mutate resources (delete, tag, etc.), if it
    supports it.

    Credentials always come from the ambient chain (whoever is logged in),
    never from awsx itself - see `awsx whoami` to confirm identity.

    Set AWSX_READONLY=1 (or run the `awsx-ro` entrypoint) to lock the whole
    session to query-only recipes - see the README for the security caveat
    on that.

    Every invocation is appended to a local audit log (see README) so a
    shared bastion has a record of who ran what.

    Output is JSON, so it pipes cleanly into jq:

        awsx --compact cleanup orphaned-snapshots --region us-east-1 | jq '.orphaned_snapshots[].SnapshotId'
    """
    ctx.ensure_object(dict)
    ctx.obj["profile"] = profile
    ctx.obj["region"] = region
    ctx.obj["dry_run"] = not execute_
    ctx.obj["pretty"] = pretty


@main.command("list-recipes")
def list_recipes():
    """List every available recipe and what it does."""
    for key, recipe in sorted(all_recipes().items()):
        tag = " [mutating]" if recipe.mutating else " [query-only]"
        click.echo(f"{key:40s}{tag:14s} {recipe.summary}")


@main.command("whoami")
@click.pass_context
def whoami(ctx):
    """Show exactly which AWS identity and OS user awsx is running as.

    This is the transparency check for "whose permissions are flowing
    through" on a shared bastion - it shows the real AWS principal (never
    an awsx-owned identity, since awsx has none) plus the local OS user.
    """
    session = base_session(ctx.obj["profile"])
    identity = get_caller_identity(session)
    info = {
        "os_user": getpass.getuser(),
        "sudo_user": _os.environ.get("SUDO_USER"),
        "hostname": socket.gethostname(),
        "aws_account": identity.get("Account"),
        "aws_arn": identity.get("Arn"),
        "aws_user_id": identity.get("UserId"),
        "profile_in_use": ctx.obj["profile"] or "(ambient/default credential chain)",
        "readonly_mode": mode.is_readonly(),
    }
    if "error" in identity:
        info["identity_error"] = identity["error"]
    click.echo(json.dumps(info, indent=2 if ctx.obj["pretty"] else None))


# Build a click sub-group per recipe group (cleanup, security, cost, crossaccount, ...)
_subgroups: dict[str, click.Group] = {}
for group_name in groups():
    grp = click.Group(name=group_name, help=f"{group_name} recipes")
    main.add_command(grp)
    _subgroups[group_name] = grp

for key, recipe in all_recipes().items():
    _subgroups[recipe.group].add_command(_make_command(recipe))


def main_readonly():
    """Entrypoint for the locked-down, query-only edition (`awsx-ro`).

    Forces read-only mode before any command logic runs, overwriting
    whatever the calling shell's environment had. Give this binary (not
    `awsx`) to users who should only be able to query, never mutate - see
    the README for how far this guarantee does and doesn't reach.
    """
    mode.lock_readonly()
    main(prog_name="awsx-ro")


if __name__ == "__main__":
    main()
