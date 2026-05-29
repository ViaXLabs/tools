# =============================================================================
# Module: nr_policy
# Creates: alert policy
# Tagging: null_resource + Python NerdGraph (issue #2492 — no entity_guid)
# =============================================================================

locals {
  prefix = "${var.team}-${var.environment}"
  common_tags = merge(
    { team = var.team, environment = var.environment },
    var.extra_tags
  )
  # Build extra-tags string for CLI — exclude team/environment (passed via env vars)
  extra_tags_cli = join(" ", [
    for k, v in local.common_tags : "${k}=${v}"
    if k != "team" && k != "environment"
  ])
}

resource "newrelic_alert_policy" "this" {
  account_id          = var.account_id
  name                = "${local.prefix}-alert-policy"
  incident_preference = "PER_CONDITION"
}

resource "null_resource" "tag_policy" {
  count = var.enable_nerdgraph_tagging ? 1 : 0

  triggers = {
    policy_id = newrelic_alert_policy.this.id
    tags_hash = jsonencode(local.common_tags)
  }

  provisioner "local-exec" {
    command = <<-EOT
      python3 "${var.script_file}" \
        --from-env \
        --policy-name "${newrelic_alert_policy.this.name}" \
        ${local.extra_tags_cli != "" ? "--extra-tags ${local.extra_tags_cli}" : ""}
    EOT
    environment = {
      NR_API_KEY     = var.nr_api_key
      NR_ACCOUNT_ID  = var.account_id
      NR_TEAM        = var.team
      NR_ENVIRONMENT = var.environment
      NR_REGION      = var.nr_region
    }
  }

  depends_on = [newrelic_alert_policy.this]
}
