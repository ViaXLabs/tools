# =============================================================================
# Module: nr_workflow
# Creates: workflow + optional muting rule
# Tagging: null_resource + Python NerdGraph (no entity_guid exported)
# =============================================================================

locals {
  prefix = "${var.team}-${var.environment}"
  common_tags = merge(
    { team = var.team, environment = var.environment },
    var.extra_tags
  )
  extra_tags_cli = join(" ", [
    for k, v in local.common_tags : "${k}=${v}"
    if k != "team" && k != "environment"
  ])
}

resource "newrelic_workflow" "this" {
  account_id            = var.account_id
  name                  = "${local.prefix}-workflow"
  muting_rules_handling = "NOTIFY_ALL_ISSUES"

  issues_filter {
    name = "${local.prefix}-filter"
    type = "FILTER"

    predicate {
      attribute = "accumulations.tag.team"
      operator  = "EXACTLY_MATCHES"
      values    = [var.team]
    }

    predicate {
      attribute = "accumulations.tag.environment"
      operator  = "EXACTLY_MATCHES"
      values    = [var.environment]
    }
  }

  destination {
    channel_id            = var.channel_id
    notification_triggers = ["ACTIVATED", "ACKNOWLEDGED", "CLOSED"]
  }
}

resource "null_resource" "tag_workflow" {
  count = var.enable_nerdgraph_tagging ? 1 : 0

  triggers = {
    workflow_id = newrelic_workflow.this.id
    tags_hash   = jsonencode(local.common_tags)
  }

  provisioner "local-exec" {
    command = <<-EOT
      python3 "${var.script_file}" \
        --from-env \
        --workflow-name "${newrelic_workflow.this.name}" \
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

  depends_on = [newrelic_workflow.this]
}

resource "newrelic_alert_muting_rule" "this" {
  count = var.create_muting_rule ? 1 : 0

  account_id  = var.account_id
  name        = "${local.prefix}-maintenance-window"
  enabled     = var.muting_rule_enabled
  description = "Mutes ${var.team}/${var.environment} alerts during deployments"

  condition {
    conditions {
      attribute = "tags.team"
      operator  = "EQUALS"
      values    = [var.team]
    }
    conditions {
      attribute = "tags.environment"
      operator  = "EQUALS"
      values    = [var.environment]
    }
    operator = "AND"
  }

  dynamic "schedule" {
    for_each = var.muting_schedule != null ? [var.muting_schedule] : []
    content {
      start_time         = schedule.value.start_time
      end_time           = schedule.value.end_time
      time_zone          = schedule.value.time_zone
      repeat             = lookup(schedule.value, "repeat", null)
      weekly_repeat_days = lookup(schedule.value, "weekly_repeat_days", null)
      repeat_count       = lookup(schedule.value, "repeat_count", null)
    }
  }
}
