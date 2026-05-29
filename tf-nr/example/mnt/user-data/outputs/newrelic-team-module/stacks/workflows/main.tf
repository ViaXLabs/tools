# Stack: workflows
# DEPENDS ON: destinations stack (reads channel_id via remote state)
# Tagging: null_resource inside nr_workflow module calls nr_tag_resources.py via local-exec.

data "terraform_remote_state" "destinations" {
  backend = "s3"
  config = {
    bucket         = var.state_bucket
    key            = "newrelic/destinations/terraform.tfstate"
    region         = var.state_region
    dynamodb_table = "terraform-state-lock"
  }
  workspace = "${var.team}-${var.environment}"
}

module "workflow" {
  source = "../../modules/nr_workflow"

  account_id  = var.newrelic_account_id
  team        = var.team
  environment = var.environment
  channel_id  = data.terraform_remote_state.destinations.outputs.channel_id
  extra_tags  = var.extra_tags

  enable_nerdgraph_tagging = var.enable_nerdgraph_tagging
  nr_api_key               = var.newrelic_api_key
  nr_region                = var.newrelic_region

  # Path from stacks/workflows/ up to repo root
  script_file = "${path.root}/../../nr_tag_resources.py"

  create_muting_rule  = var.create_muting_rule
  muting_rule_enabled = var.muting_rule_enabled
  muting_schedule     = var.muting_schedule
}

output "workflow_id"    { value = module.workflow.workflow_id }
output "workflow_name"  { value = module.workflow.workflow_name }
output "muting_rule_id" { value = module.workflow.muting_rule_id }
output "tags_applied" {
  description = "Tags applied to workflow"
  value       = module.workflow.tags_applied
}
