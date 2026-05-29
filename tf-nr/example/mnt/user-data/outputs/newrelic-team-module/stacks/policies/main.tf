# Stack: policies
# No dependencies on other stacks.
# Tagging: null_resource inside nr_policy module calls nr_tag_resources.py via local-exec.

module "policy" {
  source = "../../modules/nr_policy"

  account_id  = var.newrelic_account_id
  team        = var.team
  environment = var.environment
  extra_tags  = var.extra_tags

  enable_nerdgraph_tagging = var.enable_nerdgraph_tagging
  nr_api_key               = var.newrelic_api_key
  nr_region                = var.newrelic_region

  # Path from stacks/policies/ up to repo root where script lives
  script_file = "${path.root}/../../nr_tag_resources.py"
}

output "policy_id"   { value = module.policy.policy_id }
output "policy_name" { value = module.policy.policy_name }
output "tags_applied" {
  description = "Tags applied to alert policy"
  value       = module.policy.tags_applied
}
