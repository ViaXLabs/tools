# Least-privilege Vault policy: read-only access to exactly one KV v2 path.
#
# Attach this to whichever auth role the app uses (AppRole for VMs, Kubernetes auth role for
# k8s — see README.md Part 2, Question 1) and nothing else. This is what keeps a compromised
# app credential from turning into "now they can read every secret in the vault" — the
# blast radius of a leak is capped at this one key.

path "kv/data/prod/newrelic" {
  capabilities = ["read"]
}

# Optional: lets the app/agent see version metadata (created_time, version number) without
# granting write/delete on it.
path "kv/metadata/prod/newrelic" {
  capabilities = ["read"]
}

# --- Wiring this up (run once per environment) ---
#
#   vault policy write newrelic-read vault-policy-newrelic.hcl
#
#   # Kubernetes workloads:
#   vault write auth/kubernetes/role/my-service \
#     bound_service_account_names=my-service \
#     bound_service_account_namespaces=prod \
#     policies=newrelic-read \
#     ttl=1h
#
#   # VM / non-k8s workloads (AppRole):
#   vault write auth/approle/role/my-service \
#     policies=newrelic-read \
#     token_ttl=1h \
#     token_max_ttl=4h
#   vault read auth/approle/role/my-service/role-id            # not sensitive, can go in config mgmt
#   vault write -f auth/approle/role/my-service/secret-id       # sensitive — deliver once, wrapped
