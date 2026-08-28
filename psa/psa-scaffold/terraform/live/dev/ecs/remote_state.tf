# ROOT: terraform/live/dev/ecs (remote_state.tf)
# Reads foundation's outputs (workload_role_arn, nexus_pull_secret_arn,
# db_secret_arn) instead of recreating any of them. The "key" below MUST
# match foundation/backend.tf's key exactly, or this will fail to find
# that state (or silently read the wrong one, if you've made this same
# mistake in more than one place -- double check both).

data "terraform_remote_state" "foundation" {
  backend = "s3"
  config = {
    bucket = "psa-tfstate"
    key    = "psa/dev/foundation/terraform.tfstate"
    region = "us-east-1"
  }
}
