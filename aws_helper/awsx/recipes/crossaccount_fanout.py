"""crossaccount.fanout

Runs any other registered recipe across multiple regions and/or multiple
accounts (via assume-role) concurrently, and merges the results.

This is the "orchestration" layer -- it doesn't duplicate logic, it just
wraps whatever recipe you already have.
"""
from __future__ import annotations
import json
import click
from awsx.registry import register, get, all_recipes
from awsx.aws import all_regions, fan_out_regions, fan_out_accounts, assumed_session
from awsx import mode


@register(
    name="fanout",
    group="crossaccount",
    summary="Run a recipe across many regions and/or many accounts (assume-role) at once",
    params=[
        click.Option(["--target"], required=True,
                      help="Recipe to run, as group.name e.g. cleanup.orphaned-snapshots"),
        click.Option(["--regions"], default=None,
                      help="Comma-separated regions, or 'all' for every enabled region"),
        click.Option(["--role-arns-json"], default=None,
                      help='JSON map of account_label -> role_arn, e.g. \'{"prod":"arn:aws:iam::111:role/awsx"}\''),
        click.Option(["--target-args-json"], default="{}",
                      help="JSON of extra kwargs to pass to the target recipe"),
    ],
)
def run(session, region, dry_run, target=None, regions=None, role_arns_json=None,
        target_args_json="{}", **kwargs):
    group, _, name = target.partition(".")
    recipe = get(group, name)
    if recipe is None:
        available = ", ".join(sorted(all_recipes().keys()))
        return {"error": f"Unknown target recipe '{target}'. Available: {available}"}

    # fanout calls recipe.func() directly, bypassing the normal per-command
    # readonly check in cli.py, so it needs its own guard.
    if recipe.mutating and mode.is_readonly():
        return {"error": f"'{target}' is a mutating recipe; refusing to fan it out in read-only mode"}

    extra_args = json.loads(target_args_json)

    def run_one(sess, reg):
        return recipe.func(sess, reg, dry_run, **extra_args)

    region_list = None
    if regions:
        region_list = all_regions(session) if regions == "all" else [r.strip() for r in regions.split(",")]

    # Case 1: multiple accounts (each optionally fanned across regions too)
    if role_arns_json:
        role_arns = json.loads(role_arns_json)

        def per_account(acct_session):
            if region_list:
                return fan_out_regions(acct_session, region_list, run_one)
            return run_one(acct_session, region)

        return fan_out_accounts(session, role_arns, per_account)

    # Case 2: single account, multiple regions
    if region_list:
        return fan_out_regions(session, region_list, run_one)

    # Case 3: no fan-out requested, just run once
    return run_one(session, region)
