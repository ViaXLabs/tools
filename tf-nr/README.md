# New Relic Team Alerting Module

A Terraform module that creates and tags all alerting infrastructure for a team
in New Relic: alert policy, alert conditions, notification destination, channel,
workflow, and an optional muting rule.

---

## Tagging — the honest breakdown

Every resource type has a different tagging story. This is the result of
researching the provider source, registry docs, and several GitHub issues.

### Per-resource matrix

| Resource                            | Tagging method                                           | Why                                                                                                                                                                                                                                                                                                                |
| ----------------------------------- | -------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `newrelic_nrql_alert_condition`     | `newrelic_entity_tags` + `timeouts { create }`           | Exports `entity_guid` directly. Timeout added defensively — catalog lag is platform-wide and can bite conditions under high parallelism.                                                                                                                                                                           |
| `newrelic_notification_destination` | `newrelic_entity_tags` + `timeouts { create }`           | Was misdiagnosed as a provider bug for years. Actually NR entity catalog eventual consistency (~60-70s lag). Timeout makes Terraform retry until the tag lands, then stops immediately. [issue #2886](https://github.com/newrelic/terraform-provider-newrelic/issues/2886)                                         |
| `newrelic_alert_policy`             | `null_resource` + Python NerdGraph **or** pipeline stage | Fundamentally different problem — the resource does not export `entity_guid` at all. A `newrelic_entity` data source lookup also fails (no retry on the lookup itself). NerdGraph called from Python is the only reliable path. [issue #2492](https://github.com/newrelic/terraform-provider-newrelic/issues/2492) |
| `newrelic_workflow`                 | `issues_filter` predicate (`accumulations.tag.team`)     | No entity GUID exposed. The filter predicate IS the team association — the workflow routes issues by matching the `team` tag on the conditions that fired.                                                                                                                                                         |
| `newrelic_alert_muting_rule`        | `condition { attribute = "tags.team" }` inline           | Uses its own condition syntax natively. No `newrelic_entity_tags` needed or possible — the resource only exports `id`. The muting rule is already team-scoped via its condition.                                                                                                                                   |
| `newrelic_notification_channel`     | Not taggable                                             | No entity GUID exposed by provider.                                                                                                                                                                                                                                                                                |

### The key distinction everyone gets confused by

`newrelic_notification_destination` and `newrelic_alert_policy` both fail with
`newrelic_entity_tags`, but for completely different reasons:

- **Destination** — catalog lag. The GUID exists and is exported. `timeouts { create = "5m" }` fixes it entirely. No Python needed.
- **Alert policy** — missing GUID. The resource simply doesn't export one. No amount of waiting helps. NerdGraph is required.

### Why `timeouts` on every `newrelic_entity_tags`

The timeout is applied universally (controlled by `var.tag_timeout`, default `"5m"`) rather than only on destinations. Reasoning:

1. NR's entity catalog lag is a **platform-wide** behavior, not specific to destinations.
2. Under parallelism (multiple teams applied simultaneously) any entity type can hit it.
3. The timeout costs **nothing** when not needed — Terraform stops retrying the moment the tag confirms.
4. A single variable controls all of them, so tuning for EU region or large applies is one line.

### Anti-pattern to never do

Never use `for_each` or `count` on `newrelic_entity_tags` itself (one resource
per tag key). That creates parallel writes to the same entity GUID and they race
each other, causing intermittent failures. Always: **one `newrelic_entity_tags`
per entity, all tags inside a single `dynamic "tag"` block**.
[issue #1556](https://github.com/newrelic/terraform-provider-newrelic/issues/1556)

---

## Alert policy tagging — two approaches

### Approach A: Inline `null_resource` (default)

Set `enable_nerdgraph_tagging = true` (default). Terraform runs
`nr_tag_resources.py` via `local-exec` after the policy is created. Single
`terraform apply` does everything.

**Requires:** `python3` + `pip install requests` on the Terraform runner.

### Approach B: Separate pipeline stage

Set `enable_nerdgraph_tagging = false`. Terraform creates resources only.
A post-apply step runs `nr_tag_resources.py` reading `terraform output -json`.
See `harness-pipeline.yaml` for the full two-stage Harness setup.

**Requires:** Nothing special on the Terraform runner. Python runs in its own
pipeline container.

---

## File structure

```
newrelic-team-module/
├── README.md
├── main.tf                          # root — calls the module for each team
├── variables.tf                     # root variables
├── nr_tag_resources.py              # NerdGraph policy tagger (Approaches A + B)
├── harness-pipeline.yaml            # two-stage Harness pipeline (Approach B)
└── modules/
    └── newrelic_team_alerting/
        ├── main.tf                  # all NR resources + tagging logic
        ├── variables.tf             # all module inputs
        └── outputs.tf               # IDs/GUIDs for pipeline consumption
```

---

## Usage

```hcl
module "platform_team" {
  source = "./modules/newrelic_team_alerting"

  # Core
  account_id  = var.newrelic_account_id
  team        = "platform"
  alert_email = "platform-oncall@example.com"
  app_name    = "platform-api"

  # Extra tags applied to everything alongside the team tag
  extra_tags = {
    env         = "production"
    cost_center = "eng-platform"
  }

  # Tagging timeout — applied to all newrelic_entity_tags resources
  # Increase if you see intermittent failures on large parallel applies
  tag_timeout = "5m"

  # Alert policy NerdGraph tagging (Approach A — inline)
  enable_nerdgraph_tagging = true
  nr_api_key               = var.newrelic_api_key
  nr_region                = "US"

  # Muting rule — create it disabled; flip muting_rule_enabled=true per deploy
  create_muting_rule  = true
  muting_rule_enabled = false

  # Optional scheduled muting window
  muting_schedule = {
    start_time         = "2024-01-01T02:00:00"
    end_time           = "2024-01-01T04:00:00"
    time_zone          = "America/New_York"
    repeat             = "WEEKLY"
    weekly_repeat_days = ["TUESDAY"]
    repeat_count       = null
  }
}
```

---

## What gets created per team

| Resource                            | Name                        | Tagging approach                                                              |
| ----------------------------------- | --------------------------- | ----------------------------------------------------------------------------- |
| `newrelic_notification_destination` | `{team}-email-destination`  | `newrelic_entity_tags` + `timeouts { create = var.tag_timeout }`              |
| `newrelic_notification_channel`     | `{team}-email-channel`      | Not taggable                                                                  |
| `newrelic_alert_policy`             | `{team}-alert-policy`       | NerdGraph via Python (`null_resource` or pipeline stage)                      |
| `newrelic_nrql_alert_condition`     | `{team}-high-error-rate`    | `newrelic_entity_tags` + `timeouts { create = var.tag_timeout }`              |
| `newrelic_nrql_alert_condition`     | `{team}-high-latency`       | `newrelic_entity_tags` + `timeouts { create = var.tag_timeout }`              |
| `newrelic_workflow`                 | `{team}-workflow`           | `issues_filter` predicate (`accumulations.tag.team`)                          |
| `newrelic_alert_muting_rule`        | `{team}-maintenance-window` | `condition { attribute = "tags.team" }` — no separate tagging resource needed |

---

## Key variables

| Variable                   | Default    | Description                                                                   |
| -------------------------- | ---------- | ----------------------------------------------------------------------------- |
| `team`                     | required   | Team name — used as tag value and resource name prefix                        |
| `alert_email`              | required   | Email for alert notifications                                                 |
| `app_name`                 | `"my-app"` | App name in New Relic (used in NRQL queries)                                  |
| `extra_tags`               | `{}`       | Additional tags merged with `team` tag                                        |
| `tag_timeout`              | `"5m"`     | Timeout for all `newrelic_entity_tags` create operations                      |
| `enable_nerdgraph_tagging` | `true`     | `true` = inline Python tagging of policy; `false` = skip (use pipeline)       |
| `nr_api_key`               | `""`       | NR User API key for NerdGraph (needed when `enable_nerdgraph_tagging = true`) |
| `nr_region`                | `"US"`     | NR region for NerdGraph endpoint (`US` or `EU`)                               |
| `create_muting_rule`       | `false`    | Whether to create the muting rule resource                                    |
| `muting_rule_enabled`      | `false`    | Whether the muting rule is actively muting                                    |
| `muting_schedule`          | `null`     | Optional schedule object for the muting window                                |

---

## Source references

| Topic                                                | Link                                                                                              |
| ---------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| `newrelic_entity_tags` resource docs                 | https://registry.terraform.io/providers/newrelic/newrelic/latest/docs/resources/entity_tags       |
| `newrelic_alert_condition` entity_guid               | https://registry.terraform.io/providers/newrelic/newrelic/latest/docs/resources/alert_condition   |
| Destination catalog lag (issue #2886)                | https://github.com/newrelic/terraform-provider-newrelic/issues/2886                               |
| Alert policy missing entity_guid (issue #2492)       | https://github.com/newrelic/terraform-provider-newrelic/issues/2492                               |
| for_each anti-pattern (issue #1556)                  | https://github.com/newrelic/terraform-provider-newrelic/issues/1556                               |
| `newrelic_workflow` filter docs                      | https://registry.terraform.io/providers/newrelic/newrelic/latest/docs/resources/workflow          |
| `newrelic_alert_muting_rule` docs                    | https://registry.terraform.io/providers/newrelic/newrelic/latest/docs/resources/alert_muting_rule |
| `newrelic_service_level` sli_guid trap (issue #2633) | https://github.com/newrelic/terraform-provider-newrelic/issues/2633                               |
