# Vault Agent config for the ECS sidecar container (see ecs-task-definition-vault-sidecar.json).
#
# Authenticates using the AWS IAM auth method, backed by the ECS task's own IAM role —
# no bootstrap secret to distribute. This is ECS's version of the same trick Kubernetes
# does with a pod's service account token: the platform already gave this workload a
# verifiable identity, so Vault trusts that instead of a credential you'd have to hand it.
#
# Run with:  vault agent -config=/vault/config/agent.hcl -exit-after-auth
# -exit-after-auth makes the agent authenticate, render the template ONCE, then exit —
# paired with "dependsOn: SUCCESS" on the app container in the task definition, so the
# app only starts after the secret file exists (and doesn't start at all if the agent
# fails to authenticate — fail closed, not open).

auto_auth {
  method "aws" {
    mount_path = "auth/aws"
    config = {
      type   = "iam"
      role   = "my-service"     # Vault role bound to this task's IAM role ARN (see below)
      region = "us-east-1"
    }
  }

  sink "file" {
    config = {
      path = "/vault/secrets/.token"
      mode = 0600
    }
  }
}

vault {
  address = "https://vault.internal.example.com:8200"
}

template {
  source      = "/vault/config/newrelic.ini.ctmpl"   # reuse the same .ctmpl from the kit
  destination = "/vault/secrets/newrelic.ini"
  perms       = "0600"
}

# --- Wiring this up on the Vault side (run once per environment) ---
#
#   vault auth enable aws
#   vault write auth/aws/role/my-service \
#     auth_type=iam \
#     bound_iam_principal_arn="arn:aws:iam::123456789012:role/my-service-task-role" \
#     policies=newrelic-read \
#     ttl=1h
#
# my-service-task-role is the ECS *task role* (taskRoleArn in the task definition) —
# not the task execution role. The execution role is what ECS itself uses to pull the
# image and write logs; the task role is what your application/sidecar uses at runtime,
# and that's the identity Vault is checking here.
