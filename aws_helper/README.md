# awsx

An extensible AWS helper CLI for operations that are too intricate for
plain `aws` CLI one-liners — cross-referencing multiple API calls, fanning
out across regions/accounts, and auditing/cleanup logic — while staying
easy to extend as AWS changes. Designed to live on a shared bastion/jumpbox.

## Why this design

- **Built on boto3, not raw APIs.** You inherit AWS's own SDK updates by
  running `pip install --upgrade boto3` — no code of ours goes stale when
  AWS adds a field or a service.
- **Plugin/recipe architecture.** Every operation ("recipe") lives in its
  own file under `awsx/recipes/`, self-registers via a decorator, and is
  auto-discovered at startup. Adding a new capability = adding one file.
  Nothing else to touch, ever.
- **JSON output by default.** Everything pipes cleanly into `jq`, same as
  you'd expect from the AWS CLI itself.
- **Safe by default.** Every recipe runs read-only/dry-run unless you pass
  `--execute`.
- **No credentials of its own.** awsx never bakes in a profile, role, or
  key. It always runs as whoever is already logged in — see
  [Credentials on a shared bastion](#credentials-on-a-shared-bastion).
- **Works with no internet access.** See [Bastion / offline install](#bastion--offline-install).

## Install

```bash
pip install -e .
```

(Requires Python 3.9+, `boto3`, `click`.)

Or, to run without installing:
```bash
python -m awsx.cli --help
```

## Usage

```bash
# See everything available
awsx list-recipes

# Read-only preview (default) — find orphaned snapshots
awsx --profile prod --region us-east-1 cleanup orphaned-snapshots

# Actually delete them
awsx --profile prod --region us-east-1 cleanup orphaned-snapshots --execute

# Pipe compact JSON into jq
awsx --compact security open-security-groups --region us-east-1 \
  | jq '.security_groups[] | select(.in_use == false)'

# Fan out any recipe across every enabled region
awsx crossaccount fanout \
  --target cleanup.unattached-volumes \
  --regions all

# Fan out across accounts via assume-role, and across regions within each
awsx crossaccount fanout \
  --target security.open-security-groups \
  --role-arns-json '{"prod":"arn:aws:iam::111111111111:role/awsx-audit","staging":"arn:aws:iam::222222222222:role/awsx-audit"}' \
  --regions us-east-1,us-west-2
```

## Credentials on a shared bastion

awsx never carries its own AWS credentials, and `--profile` is optional,
not required. If you don't pass `--profile`, boto3 resolves credentials
the normal way: environment variables, `~/.aws/credentials`, AWS SSO
session, assumed role, or the EC2/ECS instance profile — whatever the
person is *already* logged in as. That's what makes this work correctly
when multiple people share one bastion, each with their own IAM
permissions: awsx just inherits whatever identity is active in that
person's shell/session. Nothing to configure per-user.

To confirm exactly whose permissions a session is using at any point:

```bash
awsx whoami
```

```json
{
  "os_user": "jsmith",
  "sudo_user": null,
  "hostname": "bastion-prod-01",
  "aws_account": "123456789012",
  "aws_arn": "arn:aws:sts::123456789012:assumed-role/DevOps-ReadWrite/jsmith",
  "aws_user_id": "AROAEXAMPLE:jsmith",
  "profile_in_use": "(ambient/default credential chain)",
  "readonly_mode": false
}
```

That `aws_arn` is the actual principal every subsequent AWS call will run
as — it's the same identity `aws sts get-caller-identity` would show you.

## Audit log (multi-user bastion trail)

Every recipe invocation appends one JSON line to a local audit log —
timestamp, OS user, AWS ARN in use, recipe name, region, dry-run/execute,
and params. This exists specifically because a bastion is shared: you get
a record of who ran what, under which permissions, without changing how
anyone uses the tool.

- Default path: `/var/log/awsx/audit.log` if writable, else
  `~/.awsx/audit.log`
- Override: `export AWSX_AUDIT_LOG=/path/to/file.log`
- Logging failures never block a command — awsx warns once on stderr and
  continues.

```bash
tail -f /var/log/awsx/audit.log | jq .
```

## Read-only / limited "query only" edition

For people who should only be able to look, not touch, use the `awsx-ro`
entrypoint instead of `awsx`:

```bash
awsx-ro security open-security-groups --region us-east-1   # works
awsx-ro cleanup orphaned-snapshots --execute                # refused
```

Under the hood: every recipe declares `mutating=True` or `False` at
registration time. `awsx-ro` forces read-only mode before any command
logic runs, and any mutating recipe is refused — even via
`crossaccount fanout`, even if someone passes `--execute`. You can also
set `AWSX_READONLY=1` yourself to get the same effect from the regular
`awsx` binary.

**Important caveat:** this is a client-side safety rail, not a security
boundary. Anyone with general shell/Python access on the bastion could,
in principle, import `awsx.cli.main` directly and bypass `awsx-ro`, or
just `unset AWSX_READONLY`. If you need a *guarantee* that a given user
cannot mutate resources, that has to come from IAM: give their role a
policy that simply lacks the mutating permissions (`ec2:DeleteSnapshot`,
`ec2:CreateTags`, etc). Use `awsx-ro` for good UX and to prevent
accidental slips, and use IAM for the actual guarantee. Pairing it with a
restricted shell (`rbash`) or a sudoers entry that only allows invoking
`awsx-ro` adds another practical layer, but IAM is still the backstop.

## Bastion / offline install

Many bastions already have `python3` and often `boto3`/awscli
preinstalled — in that case `pip install -e .` (network permitting) is
all you need, same as before.

If the bastion has **no internet access** at all (common for locked-down
jump hosts that only reach AWS API endpoints via VPC endpoints), vendor
everything on a connected machine first:

```bash
# On a machine WITH internet access (match the bastion's Python/arch):
./scripts/build_offline_bundle.sh 3.11 manylinux2014_x86_64
# produces awsx-offline-bundle.tar.gz

# Copy that one file to the bastion (scp / S3 / your usual path), then on
# the bastion itself, with no internet access required:
./scripts/install_offline.sh /opt/awsx
```

This installs `awsx` and `awsx-ro` as plain shell wrappers that run
`python3 -m awsx.cli` against the vendored dependencies — no `pip
install`, no site-packages writes, no root required. The install script
prints the `PATH`/`PYTHONPATH` lines to add to `/etc/profile.d/` for all
users, or an individual's shell rc.

To hand specific users the query-only edition, only put
`/opt/awsx/bin/awsx-ro` on their `PATH` (see the caveat above on why that
alone isn't a hard guarantee).

## Built-in recipes

| Recipe | Mutating? | What it does |
|---|---|---|
| `cleanup orphaned-snapshots` | yes (`--execute` deletes) | EBS snapshots whose source volume no longer exists |
| `cleanup unattached-volumes` | yes (`--execute` tags) | Unattached EBS volumes, age + rough cost estimate |
| `security open-security-groups` | no — query only | SGs open to 0.0.0.0/0 on sensitive ports, with attached ENIs |
| `security public-s3-buckets` | no — query only | Buckets actually public once ACL + policy + block-settings are combined |
| `cost idle-resources` | no — query only | EC2/RDS with low average CPU over a lookback window (CloudWatch) |
| `crossaccount fanout` | depends on target | Run any of the above across many regions and/or accounts at once |

Run `awsx list-recipes` to see this same table live, generated straight
from the registry (so it can never drift from what's actually installed).

## Adding a new recipe (this is the whole extension model)

Create `awsx/recipes/my_new_thing.py`:

```python
import click
from awsx.registry import register
from awsx.aws import client

@register(
    name="my-thing",              # -> `awsx <group> my-thing`
    group="cleanup",              # existing or brand-new group name
    summary="One-line description shown in `awsx list-recipes`",
    params=[
        click.Option(["--some-flag"], type=int, default=10),
    ],
    mutating=True,  # set True if this can ever delete/tag/modify anything;
                    # leave False (default) for pure describe/list/get recipes.
                    # This is what awsx-ro / AWSX_READONLY uses to decide
                    # what to block.
)
def run(session, region, dry_run, some_flag=10, **kwargs):
    svc = client(session, "some-service", region)
    # ... do the intricate multi-call logic here ...
    return {"result": "whatever JSON-serializable data you want"}
```

That's it — no registration step, no editing `cli.py`. It's auto-discovered
and immediately shows up as `awsx cleanup my-thing --some-flag 5`.

If AWS ships a new service or changes an API shape, you either:
1. Update the one recipe file that touches it, or
2. Add a brand-new recipe file for the new capability.

The core (`cli.py`, `registry.py`, `aws.py`) never needs to change for that.

## Notes / next steps

- This was scaffolded and syntax-checked (including the readonly gate,
  audit logging, and fanout guard, which were exercised directly) in an
  environment without network access, so it hasn't been run against live
  AWS or a real `boto3`/`click` install yet — please run `awsx whoami` and
  `awsx list-recipes` first thing on the actual bastion to confirm it
  behaves as expected, and let me know if anything needs adjusting.
- Cost estimates in `cleanup unattached-volumes` are rough constants, not
  live pricing — swap in the Pricing API if you want it precise.
- `scripts/build_offline_bundle.sh` pins an explicit dependency list for
  boto3/click as of writing. If a future boto3 release adds a new
  transitive dependency, run it once without `--no-deps` to see what
  landed, then re-pin.
- The audit log and `--readonly` mode are both file-based/client-side by
  design (no extra service to run on the bastion). If you later want
  centralized audit logging across many bastions, point
  `AWSX_AUDIT_LOG` at a mounted shared path, or forward
  `/var/log/awsx/audit.log` via your existing log shipper (CloudWatch
  Logs agent, etc.) — awsx doesn't need any code changes for that.
