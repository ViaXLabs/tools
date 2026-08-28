# ROOT: terraform/live/dev/foundation (outputs.tf)
# This is the whole point of "foundation" being its own root: everything
# below is read by ecs/remote_state.tf and eks/remote_state.tf via
# terraform_remote_state, instead of ecs/eks recreating any of it.
# If you rename an output here, update both of those files too.

output "nexus_pull_secret_arn" {
  value = module.foundation.nexus_pull_secret_arn
}

output "db_endpoint" {
  value = module.foundation.db_endpoint
}

output "db_secret_arn" {
  value = module.foundation.db_secret_arn
}

output "workload_role_arn" {
  value = module.foundation.workload_role_arn
}
