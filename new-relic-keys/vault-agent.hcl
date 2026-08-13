# Vault Agent config — runs as a local daemon/sidecar process on a VM or bare-metal host.
#
# Use this pattern when you are NOT using the Kubernetes Vault Agent Injector
# (see k8s-vault-agent-injector.yaml for that case). This is the direct answer to
# "how do we use Vault in files that aren't pipelines" for anything that isn't Kubernetes.
#
# What happens: the agent authenticates to Vault once via AppRole, keeps its token
# renewed in the background, and re-renders newrelic.ini.ctmpl -> a real config file on a
# refresh interval. The application itself never talks to Vault directly, and the
# rendered file only ever exists on local disk at runtime — never in git, never in the
# deploy artifact.

pid_file = "/var/run/vault-agent.pid"

auto_auth {
  method "approle" {
    mount_path = "auth/approle"
    config = {
      role_id_file_path                   = "/etc/vault/role-id"   # not sensitive; config-mgmt delivered
      secret_id_file_path                 = "/etc/vault/secret-id" # sensitive; delivered once, wrapped
      remove_secret_id_file_after_reading = true
    }
  }

  sink "file" {
    config = {
      path = "/var/run/vault-agent-token"
      mode = 0600
    }
  }
}

vault {
  address = "https://vault.internal.example.com:8200"
}

template {
  source      = "/etc/vault/templates/newrelic.ini.ctmpl"
  destination = "/etc/newrelic-infra/newrelic-infra.ini"
  perms       = "0600"
  # Re-notify the agent process after each render so it picks up a rotated key without
  # a full restart/redeploy.
  command     = "systemctl reload newrelic-infra || true"
}
