# AWS Credential Resolution Investigation — Harness Pipeline `credential_process`

**Status:** open investigation — no root cause confirmed yet
**Owner:** Josh
**Scope:** AWS auth for CLI/API calls inside Harness pipeline templates

---

## 1. Background

The pipeline uses a credential-refreshing script that implements the AWS
`credential_process` JSON contract to supply AWS credentials for CLI/API
calls. This is baked into:

- Multiple scripts
- Some config files
- A shared Docker image
- A number of pipelines
- The underlying Harness pipeline template/image

## 2. Symptom

In certain circumstances, a profile cannot be resolved/detected. The exact
error text wasn't captured cleanly on the call — **getting the literal
error string next time it happens is the single highest-value piece of
missing information** (see Open Questions below).

The most diagnostically important detail: **some AWS commands succeed and
others fail, using what's assumed to be the same profile.** This matters
because a total credential-resolution failure would break everything
uniformly — the fact that it doesn't means credentials resolve correctly at
least some of the time. That rules out "the profile is completely broken"
and points toward something narrower: a specific IAM scope, a specific
tool/environment inconsistency, or a specific race/timing condition.

## 3. Hypotheses under consideration

| # | Hypothesis | What it would explain | How to test |
|---|---|---|---|
| 1 | IAM policy / SCP / permission boundary is narrower than assumed | Some actions denied, others allowed, consistently | `iam simulate-principal-policy`, CloudTrail |
| 2 | `HOME` / `AWS_CONFIG_FILE` / env vars inconsistent across pipeline steps or Docker layers | Profile resolves in some steps, not others | Diff env snapshots between working and failing steps |
| 3 | `credential_process` script's JSON output is malformed or has a bad/expired `Expiration` in some cases | Intermittent failures that look like "sometimes detected" | Validate JSON shape + expiry across repeated runs |
| 4 | A non-CLI tool in the pipeline (e.g. Terraform, or another SDK) doesn't fully honor the shared config file / `credential_process` the way the CLI does | Certain commands (run via a different tool) fail while CLI commands succeed | Check `AWS_SDK_LOAD_CONFIG`, identify what's actually issuing each call |
| 5 | `credential_process` output isn't cached, and concurrent pipeline steps race against the refresh script | Non-deterministic, timing-dependent failures | Fire the refresh script in parallel, compare output |
| 6 | VPC endpoint policy blocks specific actions/services | Some services fail, others succeed, independent of IAM | `ec2 describe-vpc-endpoints` and inspect policy documents |

None of these are confirmed — they're the working list of what to rule in
or out.

## 4. A clarification from the call: does "the API" use different auth than the CLI?

Not at the protocol level. AWS CLI and API calls (through any first-party
SDK) both authenticate using SigV4 signing, and if a client reads the
shared `~/.aws/config` / `~/.aws/credentials` file, `credential_process` is
honored the same way in principle.

What *does* genuinely differ, and fits the symptom well, is **which client
is making the call and whether that client's credential provider chain
fully implements the shared config spec**:

- **Go SDK v1 — and anything built on it, notably Terraform — does not read
  `~/.aws/config` at all unless `AWS_SDK_LOAD_CONFIG=1` is explicitly set**
  in the environment. If the pipeline mixes `aws` CLI steps with Terraform
  or other Go-based tooling in the same Harness template, and that env var
  isn't set consistently across every step/container layer, that alone
  would produce "some commands work, others don't."
- **The SDK does not cache `credential_process` output itself** — caching
  is the refresh script's responsibility. If two pipeline steps invoke the
  script concurrently without locking, or the script itself doesn't cache
  and each call round-trips a fresh assume-role, that's a plausible source
  of intermittent, timing-dependent failures.

This narrowed hypothesis #4 and #5 above and is why the diagnostic scripts
below specifically check `AWS_SDK_LOAD_CONFIG`, identify what tool is
issuing each call, and stress-test the refresh script under concurrency.

## 5. Manual exploration commands

Quick reference for exploring identity, resolution, and permissions by hand:

```bash
# Confirm identity actually in use (works if creds resolve at all — no
# permissions required, since it just decodes the token)
aws sts get-caller-identity --profile <profile>

# Show the SOURCE of each credential field (env / config-file / credential_process)
aws configure list --profile <profile>

# Watch credential_process resolution in detail
AWS_PROFILE=<profile> aws sts get-caller-identity --debug 2>&1 | grep -i -A 5 "credential"

# Run the refresh script standalone and validate its JSON shape
./your-refresh-script.sh | jq .
# Check for: Version, AccessKeyId, SecretAccessKey, SessionToken,
# and a properly formatted, future-dated Expiration (ISO 8601, UTC)

# Enumerate what the resolved principal can do
aws iam list-attached-user-policies --user-name <name>
aws iam list-user-policies --user-name <name>
aws iam get-user --user-name <name> --query 'User.PermissionsBoundary'
# or, for a role:
aws iam list-attached-role-policies --role-name <role>
aws iam list-role-policies --role-name <role>
aws iam get-role --role-name <role> --query 'Role.PermissionsBoundary'

# Test specific actions directly instead of guessing from CLI errors
aws iam simulate-principal-policy \
  --policy-source-arn <user-or-role-arn> \
  --action-names s3:GetObject ec2:DescribeInstances sts:AssumeRole \
  --resource-arns "*"

# Pull the real denial reason from CloudTrail (names the denying policy/SCP)
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=Username,AttributeValue=<assumed-role-session-name> \
  --max-results 20

# Check for VPC endpoint policies silently scoping allowed actions
aws ec2 describe-vpc-endpoints --query 'VpcEndpoints[].{Id:VpcEndpointId,Service:ServiceName,Policy:PolicyDocument}'

# Identify what's actually issuing a given "API" call, and whether it
# would even see AWS_SDK_LOAD_CONFIG-gated shared config
which aws; type aws
env | grep -i aws
echo $AWS_SDK_LOAD_CONFIG
terraform version   # if Terraform is in the mix
```

## 6. Diagnostic script suite

Five scripts, each isolating one hypothesis above, plus a README with the
suggested workflow. All are read-only — nothing here writes or deletes
anything in AWS.

| Script | Tests | Hypothesis |
|---|---|---|
| `00-env-snapshot.sh` | Full env/config/tooling state at the point of failure — meant to be diffed between a working step and a failing step | #2, #4 |
| `01-credential-process-check.sh` | Validates the refresh script's JSON output shape and expiry across repeated runs | #3 |
| `02-command-matrix.sh` | Runs a battery of AWS commands and auto-categorizes failures as resolution / permissions / stale-credential | All — builds the evidence base |
| `03-permission-simulate.sh` | Asks IAM directly which policy denies which action, instead of inferring from CLI errors | #1, #6 |
| `04-concurrency-race-check.sh` | Fires the refresh script in parallel to check for races/inconsistent output | #5 |

Usage details are in `README.md`, included alongside these scripts. Quick
summary of the intended flow:

1. Run `00` in both a working and a failing pipeline step → diff.
2. Run `01` against the refresh script directly → confirms/rules out a bad
   `credential_process` implementation.
3. Run `02` to get a concrete pass/fail list instead of an impression.
4. Feed `02`'s permission-flagged failures into `03`.
5. If failures look intermittent/non-deterministic, run `04`.

**Note:** the executable bit doesn't persist through this file mount — run
`chmod +x *.sh` after downloading, before use.

## 7. Open questions to bring back

- What is the **literal error text** AWS CLI returns when the profile
  "isn't detected"? (e.g. `AccessDenied`, `ExpiredToken`, `The config
  profile (X) could not be found`, `Unable to locate credentials`)
- Which specific commands fail vs. succeed, run back-to-back with the same
  profile in the same step?
- What tool/library is actually issuing "the API" calls that are suspected
  of using different auth — Terraform, a language SDK, raw HTTP? This
  determines whether hypothesis #4 (shared-config support) is even in play.
- Does the failure correlate with parallel/concurrent pipeline steps, or
  does it happen even in isolated, sequential runs?
