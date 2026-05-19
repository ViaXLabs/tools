# =============================================================================
# New Relic Team Alerting Module — main.tf
#
# TAGGING STRATEGY SUMMARY
# ─────────────────────────────────────────────────────────────────────────────
#
#  Resource                         | Tag method                        | Notes
#  ──────────────────────────────── | ──────────────────────────────────|────────
#  newrelic_nrql_alert_condition    | newrelic_entity_tags              | exports entity_guid directly
#                                   |   + timeouts { create = var.tag_timeout } | defensive: catalog lag under parallelism
#  newrelic_notification_destination| newrelic_entity_tags              | confirmed catalog lag ~60-70s
#                                   |   + timeouts { create = var.tag_timeout } | issue #2886: timeout is the official fix
#  newrelic_alert_policy            | null_resource + local-exec        | does NOT export entity_guid at all —
#                                   |   → Python NerdGraph              | fundamentally different problem, issue #2492
#                                   |   OR pipeline stage               | timeout can't help when there's no GUID
#  newrelic_workflow                | issues_filter predicate           | no entity GUID exposed; filter IS the
#                                   |   accumulations.tag.team          | team association
#  newrelic_alert_muting_rule       | condition { attribute="tags.team"}| uses its own condition syntax natively;
#                                   |                                   | no newrelic_entity_tags needed or possible
#
# WHY TIMEOUTS ON EVERY newrelic_entity_tags
# ─────────────────────────────────────────────────────────────────────────────
#  NR's entity catalog has platform-wide eventual consistency lag. It's
#  confirmed on destinations (~60-70s) and plausible on any entity type under
#  parallelism. Applying timeouts { create = var.tag_timeout } universally is
#  the simplest, most consistent approach — it costs nothing when not needed
#  (TF stops retrying the moment the tag confirms) and saves you when it is.
#  Ref: https://github.com/newrelic/terraform-provider-newrelic/issues/2886
#
# ANTI-PATTERN WARNING
# ─────────────────────────────────────────────────────────────────────────────
#  NEVER use for_each or count on newrelic_entity_tags itself (one resource
#  per tag key). That creates parallel writes to the same entity GUID and they
#  race each other. Always: ONE newrelic_entity_tags per entity, ALL tags
#  inside a single dynamic "tag" block.
#  Ref: https://github.com/newrelic/terraform-provider-newrelic/issues/1556
# =============================================================================

locals {
  common_tags = merge(
    { team = var.team },
    var.extra_tags
  )
  prefix = var.team
}

# -----------------------------------------------------------------------------
# 1. NOTIFICATION DESTINATION
#    timeouts needed: YES — catalog lag confirmed ~60-70s (issue #2886)
# -----------------------------------------------------------------------------
resource "newrelic_notification_destination" "team_email" {
  account_id = var.account_id
  name       = "${local.prefix}-email-destination"
  type       = "EMAIL"

  property {
    key   = "email"
    value = var.alert_email
  }
}

resource "newrelic_entity_tags" "destination_tags" {
  guid = newrelic_notification_destination.team_email.guid

  dynamic "tag" {
    for_each = local.common_tags
    content {
      key    = tag.key
      values = [tag.value]
    }
  }

  timeouts {
    create = var.tag_timeout
  }

  depends_on = [newrelic_notification_destination.team_email]
}

# -----------------------------------------------------------------------------
# 2. NOTIFICATION CHANNEL
#    Not a taggable entity — no GUID exposed by provider.
# -----------------------------------------------------------------------------
resource "newrelic_notification_channel" "team_email_channel" {
  account_id     = var.account_id
  name           = "${local.prefix}-email-channel"
  type           = "EMAIL"
  destination_id = newrelic_notification_destination.team_email.id
  product        = "IINT"

  property {
    key   = "subject"
    value = "[${upper(var.team)}] New Relic Alert: {{issueTitle}}"
  }

  depends_on = [newrelic_notification_destination.team_email]
}

# -----------------------------------------------------------------------------
# 3. ALERT POLICY
#    timeouts needed: N/A — no entity_guid exported at all (issue #2492).
#    timeouts { create } only helps when there IS a GUID to pass to
#    newrelic_entity_tags. Here there isn't one. NerdGraph is the only path.
# -----------------------------------------------------------------------------
resource "newrelic_alert_policy" "team_policy" {
  account_id          = var.account_id
  name                = "${local.prefix}-alert-policy"
  incident_preference = "PER_CONDITION"
}

resource "null_resource" "tag_alert_policy" {
  count = var.enable_nerdgraph_tagging ? 1 : 0

  triggers = {
    policy_id = newrelic_alert_policy.team_policy.id
    tags_hash = jsonencode(local.common_tags)
  }

  provisioner "local-exec" {
    # --policy-name triggers a NerdGraph lookup with built-in retry for lag.
    # --policy-guid is intentionally omitted so the script handles catalog lag
    # via its own retry loop rather than failing immediately.
    command = <<-EOT
      python3 ${var.script_path}/nr_tag_resources.py \
        --from-env \
        --policy-name "${newrelic_alert_policy.team_policy.name}" \
        --extra-tags ${length([for k, v in local.common_tags : "${k}=${v}" if k != "team"]) > 0 ? join(" ", [for k, v in local.common_tags : "${k}=${v}" if k != "team"]) : "noop=true"}
    EOT

    environment = {
      NR_API_KEY    = var.nr_api_key
      NR_ACCOUNT_ID = var.account_id
      NR_TEAM       = var.team
      NR_REGION     = var.nr_region
    }
  }

  depends_on = [newrelic_alert_policy.team_policy]
}

# -----------------------------------------------------------------------------
# 4. ALERT CONDITIONS
#    timeouts needed: DEFENSIVE — entity_guid exported directly so no known
#    lag, but catalog lag is a platform-wide NR behavior. Under parallelism
#    (multiple teams applied simultaneously) conditions can hit it too.
#    Cost of adding timeout = zero when not needed (TF stops immediately on
#    success). Cost of not having it = intermittent failures under load.
# -----------------------------------------------------------------------------
resource "newrelic_nrql_alert_condition" "high_error_rate" {
  account_id = var.account_id
  policy_id  = newrelic_alert_policy.team_policy.id

  name        = "${local.prefix}-high-error-rate"
  description = "Fires when error rate for ${var.app_name} exceeds threshold"
  type        = "static"
  enabled     = true

  violation_time_limit_seconds = 3600

  nrql {
    query = "SELECT percentage(count(*), WHERE error IS true) FROM Transaction WHERE appName = '${var.app_name}'"
  }

  critical {
    operator              = "above"
    threshold             = var.error_rate_threshold_critical
    threshold_duration    = 300
    threshold_occurrences = "ALL"
  }

  warning {
    operator              = "above"
    threshold             = var.error_rate_threshold_warning
    threshold_duration    = 300
    threshold_occurrences = "ALL"
  }

  fill_option = "none"
}

resource "newrelic_entity_tags" "high_error_rate_tags" {
  guid = newrelic_nrql_alert_condition.high_error_rate.entity_guid

  dynamic "tag" {
    for_each = local.common_tags
    content {
      key    = tag.key
      values = [tag.value]
    }
  }

  timeouts {
    create = var.tag_timeout
  }
}

resource "newrelic_nrql_alert_condition" "high_latency" {
  account_id = var.account_id
  policy_id  = newrelic_alert_policy.team_policy.id

  name        = "${local.prefix}-high-latency"
  description = "Fires when average response time for ${var.app_name} exceeds threshold"
  type        = "static"
  enabled     = true

  violation_time_limit_seconds = 3600

  nrql {
    query = "SELECT average(duration) FROM Transaction WHERE appName = '${var.app_name}'"
  }

  critical {
    operator              = "above"
    threshold             = var.latency_threshold_critical_seconds
    threshold_duration    = 300
    threshold_occurrences = "ALL"
  }

  warning {
    operator              = "above"
    threshold             = var.latency_threshold_warning_seconds
    threshold_duration    = 300
    threshold_occurrences = "ALL"
  }

  fill_option = "none"
}

resource "newrelic_entity_tags" "high_latency_tags" {
  guid = newrelic_nrql_alert_condition.high_latency.entity_guid

  dynamic "tag" {
    for_each = local.common_tags
    content {
      key    = tag.key
      values = [tag.value]
    }
  }

  timeouts {
    create = var.tag_timeout
  }
}

# -----------------------------------------------------------------------------
# 5. WORKFLOW
#    Not taggable via newrelic_entity_tags — no entity GUID exposed.
#    Team scoping is expressed via the issues_filter predicate instead.
#    The workflow routes any issue whose conditions carry tag team=<var.team>.
# -----------------------------------------------------------------------------
resource "newrelic_workflow" "team_workflow" {
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
  }

  destination {
    channel_id = newrelic_notification_channel.team_email_channel.id
    notification_triggers = [
      "ACTIVATED",
      "ACKNOWLEDGED",
      "CLOSED",
    ]
  }

  depends_on = [
    newrelic_notification_channel.team_email_channel,
    newrelic_entity_tags.destination_tags,
    newrelic_entity_tags.high_error_rate_tags,
    newrelic_entity_tags.high_latency_tags,
  ]
}

# -----------------------------------------------------------------------------
# 6. MUTING RULE
#    newrelic_alert_muting_rule uses its OWN condition syntax to scope by team.
#    The attribute "tags.team" inside the condition block directly matches
#    incidents whose entities carry the team tag — no newrelic_entity_tags
#    needed or possible (the resource exports only `id`, no entity GUID).
#
#    This rule is disabled by default (var.muting_rule_enabled = false).
#    Enable it during planned maintenance windows or deployments.
#
#    Ref: https://registry.terraform.io/providers/newrelic/newrelic/latest/docs/resources/alert_muting_rule
# -----------------------------------------------------------------------------
resource "newrelic_alert_muting_rule" "team_maintenance" {
  count = var.create_muting_rule ? 1 : 0

  account_id  = var.account_id
  name        = "${local.prefix}-maintenance-window"
  enabled     = var.muting_rule_enabled
  description = "Mutes ${var.team} team alerts — used during deployments and maintenance windows"

  condition {
    # Scope to this team's tagged incidents
    conditions {
      attribute = "tags.team"
      operator  = "EQUALS"
      values    = [var.team]
    }
    # AND scope to this team's policy so the rule is as narrow as possible
    conditions {
      attribute = "policyName"
      operator  = "EQUALS"
      values    = [newrelic_alert_policy.team_policy.name]
    }
    operator = "AND"
  }

  # Optional scheduled window — only applied when var.muting_schedule is set.
  # Leave unset for an always-on (when enabled=true) muting rule.
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

  depends_on = [newrelic_alert_policy.team_policy]
}
