# ── Core ──────────────────────────────────────────────────────────────────────

variable "account_id" {
  description = "The New Relic account ID"
  type        = string
}

variable "team" {
  description = "Team name — used as the 'team' tag value and as the resource name prefix (e.g. 'platform', 'checkout')"
  type        = string
}

variable "alert_email" {
  description = "Email address for alert notifications"
  type        = string
}

variable "app_name" {
  description = "Application name as it appears in New Relic (used in NRQL queries)"
  type        = string
  default     = "my-app"
}

variable "extra_tags" {
  description = "Additional tags applied to all taggable resources, merged with the team tag (e.g. { env = 'production', cost_center = 'eng-platform' })"
  type        = map(string)
  default     = {}
}

# ── Alert thresholds ──────────────────────────────────────────────────────────

variable "error_rate_threshold_critical" {
  description = "Error rate % that triggers a critical alert"
  type        = number
  default     = 5
}

variable "error_rate_threshold_warning" {
  description = "Error rate % that triggers a warning alert"
  type        = number
  default     = 2
}

variable "latency_threshold_critical_seconds" {
  description = "Average response time (seconds) that triggers a critical alert"
  type        = number
  default     = 2
}

variable "latency_threshold_warning_seconds" {
  description = "Average response time (seconds) that triggers a warning alert"
  type        = number
  default     = 1
}

# ── Tagging ───────────────────────────────────────────────────────────────────

variable "tag_timeout" {
  description = <<-EOT
    Timeout for newrelic_entity_tags create operations.
    Applied to ALL newrelic_entity_tags resources in this module (destination,
    alert conditions) as a universal defence against NR entity catalog
    eventual consistency lag.

    NR's catalog takes ~60-70s post-creation before tags can be written on some
    resource types (confirmed on destinations, plausible on any entity under
    parallelism). The timeout makes Terraform retry until the tag confirms, then
    stops immediately — so there's no cost when not needed.

    Increase if you're in EU region or seeing intermittent failures on large
    parallel applies. "5m" is safe for most cases.

    Ref: https://github.com/newrelic/terraform-provider-newrelic/issues/2886
  EOT
  type    = string
  default = "5m"
}

# ── Alert policy NerdGraph tagging ────────────────────────────────────────────
# newrelic_alert_policy does not export entity_guid, so newrelic_entity_tags
# (and therefore tag_timeout) cannot be used. The null_resource approach
# calls NerdGraph directly via Python. See issue #2492.

variable "enable_nerdgraph_tagging" {
  description = <<-EOT
    true  → tag the alert policy inline via null_resource + nr_tag_resources.py.
            Requires python3 + requests on the Terraform runner.
    false → skip inline tagging. Use nr_tag_resources.py in a separate pipeline
            step reading `terraform output -json` (see harness-pipeline.yaml).
  EOT
  type    = bool
  default = true
}

variable "nr_api_key" {
  description = "New Relic User API key (NRAK-...) for NerdGraph calls. Only needed when enable_nerdgraph_tagging = true."
  type      = string
  default   = ""
  sensitive = true
}

variable "nr_region" {
  description = "New Relic region for NerdGraph endpoint: US or EU"
  type    = string
  default = "US"
}

variable "script_path" {
  description = "Directory containing nr_tag_resources.py. Defaults to repo root (3 levels up from this module)."
  type    = string
  default = "${path.module}/../../.."
}

# ── Muting rule ───────────────────────────────────────────────────────────────

variable "create_muting_rule" {
  description = "Whether to create a muting rule resource for this team at all. Set true to create it (disabled by default via muting_rule_enabled)."
  type    = bool
  default = false
}

variable "muting_rule_enabled" {
  description = <<-EOT
    Whether the muting rule is actively muting. Separate from create_muting_rule:
    you can create the rule (create_muting_rule = true) but leave it off
    (muting_rule_enabled = false) and flip it on during deployments without
    re-running terraform apply.

    In practice: set create_muting_rule = true always, toggle muting_rule_enabled
    per deployment via your pipeline.
  EOT
  type    = bool
  default = false
}

variable "muting_schedule" {
  description = <<-EOT
    Optional schedule for the muting rule. When null the rule is always-on
    (when muting_rule_enabled = true). When set, muting only applies within
    the scheduled window.

    Example:
      muting_schedule = {
        start_time         = "2024-01-01T02:00:00"
        end_time           = "2024-01-01T04:00:00"
        time_zone          = "America/New_York"
        repeat             = "WEEKLY"
        weekly_repeat_days = ["TUESDAY"]
        repeat_count       = null
      }
  EOT
  type = object({
    start_time         = string
    end_time           = string
    time_zone          = string
    repeat             = optional(string)
    weekly_repeat_days = optional(list(string))
    repeat_count       = optional(number)
  })
  default = null
}
