# AWS credential_process diagnostics

Five small, read-only scripts to turn "some commands work, some don't" into
concrete evidence. Each targets one hypothesis from the debugging session
that produced them.

Requires `jq` (and standard GNU coreutils `date` — see note in
`01-credential-process-check.sh` if your image uses busybox/Alpine date).

## Suggested order

1. **`00-env-snapshot.sh [profile]`**
   Run once in a pipeline step that **works** and once in a step that
   **fails**, then `diff` the two output files. This alone often finds it —
   e.g. a missing `AWS_SDK_LOAD_CONFIG=1` in the failing step, an env var
   silently overriding the profile, or a `credential_process` pointing at a
   binary that isn't even on `PATH` in that particular container layer.

2. **`01-credential-process-check.sh '<refresh script command>' [iterations]`**
   Validates that your refresh script's stdout is well-formed
   `credential_process` JSON (`Version`, `AccessKeyId`, `SecretAccessKey`,
   `Expiration`, future-dated) and runs it repeatedly to catch flakiness.

3. **`02-command-matrix.sh [profile]`**
   Runs a battery of read-only AWS commands and buckets each failure as a
   **resolution** issue (profile/credential_process), a **permissions**
   issue (AccessDenied), or a **stale-credential** issue (ExpiredToken).
   Edit the `CMDS` array to mirror what your pipeline actually calls.

4. **`03-permission-simulate.sh [profile] [action ...]`**
   Feed it the actions that came back "permissions" in step 3. Asks IAM
   directly via `simulate-principal-policy` which policy is responsible,
   rather than guessing from CLI error text. Handles the assumed-role →
   underlying-role ARN conversion the simulator requires.

5. **`04-concurrency-race-check.sh '<refresh script command>' [parallelism]`**
   Fires the refresh script in parallel. The SDK does not cache
   `credential_process` output itself — your script owns that. If Harness
   runs steps concurrently against the same cache/lock file, this is where
   intermittent, hard-to-reproduce failures usually come from.

## Running these against the actual pipeline

- **Locally against the Docker image**, to reproduce without burning a
  pipeline run:
  ```bash
  docker run --rm -it --entrypoint bash <your-image>
  # copy/mount the scripts in, then run them
  ```
- **Inside Harness**, temporarily add a debug `Run` step using the same
  image/template as the failing step, and invoke the relevant script(s)
  there — the environment needs to match the failing step exactly (same
  container layer, same step type) for `00-env-snapshot.sh` to be useful as
  a diff target.

## What each failure pattern points back to

| Symptom | Likely cause |
|---|---|
| `could not be found` / `unable to locate credentials` | Profile resolution — check `00`'s output for `AWS_CONFIG_FILE` path, `AWS_SDK_LOAD_CONFIG` (if a Go-based tool like Terraform is involved), or env vars overriding the profile |
| `AccessDenied` / `not authorized` on specific actions only | IAM policy scope — run `03` |
| `ExpiredToken` / `InvalidClientTokenId`, intermittent | Refresh script's `Expiration` field or a caching/race issue — run `01` and `04` |
| Same command, same profile, different result run-to-run | Concurrency — run `04` |
