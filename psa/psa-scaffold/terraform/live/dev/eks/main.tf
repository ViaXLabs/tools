# ROOT: terraform/live/dev/eks (main.tf)
# Two apps, two module blocks, same modules/eks-workload source and same
# chart_path -- this is the pattern to copy when adding a language.
# See modules/eks-workload/variables.tf for what image_repository/
# image_tag/image_pull_secret actually do; the regex above is what turns
# one full image URI into the repository+tag pair that module expects.

locals {
  # Both apps point at the same shared chart. Adding a third language's EKS
  # deployment is another module block like these two -- nothing here or
  # in modules/eks-workload changes.
  chart_path = "${path.module}/../../../../charts/psa-service"

  # Split on the LAST colon only, not the first -- Nexus registry hosts
  # commonly include a port (nexus.company.com:8082/...), so a naive
  # split(":", uri) would wrongly split on that too. The tag itself can't
  # contain "/" or ":", so this pattern is safe.
  java_image   = regex("^(.*):([^:/]+)$", var.java_image_uri)
  python_image = regex("^(.*):([^:/]+)$", var.python_image_uri)

  # Synced into the psa-dev namespace outside Terraform (External Secrets
  # or similar) from the same Nexus credentials secret foundation reads.
  # Shared across apps since both land in the same namespace.
  nexus_pull_secret_name = "psa-nexus-pull"
}

module "java_eks" {
  source = "../../../modules/eks-workload"

  name              = "psa-java"
  environment       = "dev"
  chart_path        = local.chart_path
  image_repository  = local.java_image[0]
  image_tag         = local.java_image[1]
  irsa_role_arn     = data.terraform_remote_state.foundation.outputs.workload_role_arn
  ingress_host      = var.java_ingress_host
  image_pull_secret = local.nexus_pull_secret_name

  environment_variables = {
    NEW_RELIC_APP_NAME      = "psa-java-dev"
    NEW_RELIC_LOG_FILE_PATH = "STDOUT"
    JAVA_OPTS               = "-javaagent:/app/newrelic/newrelic.jar"
  }

  # Synced from foundation's db_secret_arn + the New Relic license key by
  # External Secrets Operator (or your team's preferred k8s secrets sync tool).
  secret_env_from = "psa-java-secrets"
}

module "python_eks" {
  source = "../../../modules/eks-workload"

  name              = "psa-python"
  environment       = "dev"
  chart_path        = local.chart_path
  image_repository  = local.python_image[0]
  image_tag         = local.python_image[1]
  irsa_role_arn     = data.terraform_remote_state.foundation.outputs.workload_role_arn
  ingress_host      = var.python_ingress_host
  image_pull_secret = local.nexus_pull_secret_name

  environment_variables = {}

  secret_env_from = "psa-python-secrets"
}
