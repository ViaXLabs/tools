# Example read-only Vault policy for the structure scanner.
# Attach this to whatever auth method/token you use for the Harness pipeline.
# Adjust the mount names ("secret", "app-configs", ...) to match each vault.

# Optional: lets the script auto-discover which mounts are KV engines instead
# of you listing them by hand in vaults.yaml. Skip this block if your Vault
# admins won't grant it - the script falls back to the explicit "mounts:"
# list in the config and probes each one individually.
path "sys/mounts" {
  capabilities = ["read"]
}

# --- KV v2 mounts ---
# v2 splits metadata (used for LIST) and data (used for READ) under the
# same mount. Both are needed: list to walk folders, read to see field
# names inside each secret.
path "secret/metadata/*" {
  capabilities = ["list", "read"]
}
path "secret/data/*" {
  capabilities = ["read"]
}

# --- KV v1 mounts ---
# v1 has one flat path namespace, so list + read cover both list and read.
path "app-configs/*" {
  capabilities = ["list", "read"]
}

# Repeat one metadata/data (v2) or flat (v1) block per KV mount you want
# this token to see. Do NOT grant "create", "update", or "delete" anywhere -
# this token should only ever be able to look, never write.
