# Vault Structure Scanner

Walks the KV folder hierarchy across multiple HashiCorp Vault clusters and
reports **structure only**: mounts, folder paths, secret names, and the
field (key) names inside each secret. Secret *values* are never read into
anything that gets printed, logged, or written to disk.

Output: an HTML report (nice for skimming, easy to publish to Confluence)
and a plain-text tree (easy to diff or grep in a pipeline log).

## Quick start (no vault needed - see the report style first)

```bash
pip install -r requirements.txt --break-system-packages   # or use a venv
python3 vault_tree_scanner.py --demo
```

This writes `vault_structure.html` and `vault_structure.txt` from built-in
sample data so you can see the formatting before wiring in real credentials.

## Real usage

1. Copy `config/vaults.example.yaml` to `config/vaults.yaml` and fill in
   your ~8-9 vaults' addresses and an env var name per vault (not the token
   itself - see below).
2. Attach a read-only policy like `policy-example.hcl` to the token/AppRole
   used for each vault.
3. Export one env var per vault holding that vault's token, matching the
   `token_env_var` name you put in the config, then run:

```bash
export VAULT_TOKEN_PROD_EU=...
export VAULT_TOKEN_PROD_US=...
python3 vault_tree_scanner.py --config config/vaults.yaml
```

### Selecting a subset of vaults

```bash
python3 vault_tree_scanner.py --config config/vaults.yaml --vaults prod-eu prod-us
```

Omit `--vaults` to scan every vault in the config.

### Other flags

| Flag | Purpose |
|---|---|
| `--out-html PATH` / `--out-text PATH` | override the output paths from config |
| `--max-depth N` | cap recursion depth (safety valve, default 25) |
| `--strict` | exit non-zero if any vault failed to auth or scan - use this in the pipeline step if a partial scan should fail the build |
| `--quiet` | only print warnings/errors |
| `-v` / `--verbose` | debug logging for this script's own messages (third-party HTTP libraries stay quiet regardless - see Security section) |

## How mounts and KV versions are handled

You didn't need to pin this down, so the script auto-detects it:

- If the token can read `sys/mounts`, the script lists all engines and
  scans every one whose type is `kv`, reading each mount's own
  `options.version` to know whether it's v1 or v2.
- If a vault's `mounts:` list is left empty in the config, this is also how
  mounts get discovered for that vault. If `sys/mounts` isn't readable
  (many locked-down policies don't allow it) and you left `mounts:` empty,
  that vault will show zero mounts - either grant `sys/mounts` read (see
  `policy-example.hcl`) or list the mount names explicitly in `mounts:`.
- If `mounts:` is filled in for a vault but `sys/mounts` isn't readable,
  the script probes each named mount individually to tell v1 from v2.

## What "just the keys" means here

For every secret found, the script reads it once, keeps `sorted(data.keys())`
and immediately discards the value dict - so a secret at `secret/app1/database`
with fields `username`, `password`, `host` shows up as:

```
└── database  [keys: username, password, host]
```

Never as `username: admin, password: hunter2, host: db.internal`.

## Security notes (read before running this in a real pipeline)

- **Tokens never touch the repo or the report.** `vaults.yaml` only names
  an environment variable per vault; the actual token value comes from
  Harness's secret manager at pipeline runtime. Don't hardcode a token in
  the YAML or pass it as a plain pipeline variable.
- **Values are never logged.** The only Vault calls made are LIST and
  READ. Every READ is immediately reduced to a list of field names in the
  same function that made the call (`_read_secret_keys` in
  `vault_tree_scanner.py`), and the original response is deleted right
  after. No log statement in the script interpolates a raw response - only
  vault/mount/path names and the exception *type* on failure.
- **Third-party HTTP debug logs are force-quieted.** `requests`, `urllib3`,
  and `hvac` can emit very verbose DEBUG logs that include full request/
  response bodies. `configure_logging()` pins those three loggers to
  WARNING regardless of the `-v` flag, so turning up this script's own
  verbosity for troubleshooting can't accidentally leak a value into CI
  logs.
- **In Harness itself:** make sure the shell step doesn't run with
  `set -x` / `bash -x` while your `export VAULT_TOKEN_...=<secret>` lines
  are inline in the script - that would print the token to the log before
  this script ever runs. Inject tokens as Harness secret variables mapped
  straight to env vars on the step instead of exporting them from a script
  line.
- **Least privilege:** the token/AppRole only needs `list` + `read` on the
  KV paths you want visibility into (see `policy-example.hcl`). It never
  needs `create`, `update`, or `delete` anywhere - this tool cannot and
  should not modify Vault contents.

## Example Harness pipeline step

Adapt to however your pipeline is structured (this assumes a Shell Script
step with the vault tokens wired in as secret variables):

```yaml
- step:
    type: ShellScript
    name: Scan Vault Structure
    spec:
      shell: Bash
      source:
        type: Inline
        spec:
          script: |
            pip install -r requirements.txt --break-system-packages -q
            python3 vault_tree_scanner.py --config config/vaults.yaml --strict
      environmentVariables:
        - name: VAULT_TOKEN_PROD_EU
          type: Secret
          value: prod_eu_vault_token
        - name: VAULT_TOKEN_PROD_US
          type: Secret
          value: prod_us_vault_token
        # ... one per vault
    # then a later step picks up vault_structure.html as an artifact/output
    # and hands it to whatever already publishes it to Confluence
```

(I don't have visibility into your actual Harness pipeline YAML structure,
so treat this as a starting shape to adapt, not a drop-in block.)

## Files in this delivery

| File | Purpose |
|---|---|
| `vault_tree_scanner.py` | the scanner itself |
| `requirements.txt` | `pip install -r` |
| `config/vaults.example.yaml` | copy to `vaults.yaml` and fill in your vaults |
| `policy-example.hcl` | least-privilege Vault ACL policy to attach to the scanning token |
| `output/sample_structure.html`, `output/sample_structure.txt` | sample report generated with `--demo`, so you can see the styling immediately |
