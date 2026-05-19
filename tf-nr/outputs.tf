output "alert_policy_id" {
  description = "ID of the alert policy"
  value       = newrelic_alert_policy.team_policy.id
}

output "alert_policy_name" {
  description = "Name of the alert policy — used by nr_tag_resources.py for NerdGraph GUID lookup"
  value       = newrelic_alert_policy.team_policy.name
}

output "notification_destination_id" {
  description = "ID of the notification destination"
  value       = newrelic_notification_destination.team_email.id
}

output "notification_destination_guid" {
  description = "Entity GUID of the notification destination"
  value       = newrelic_notification_destination.team_email.guid
}

output "notification_channel_id" {
  description = "ID of the notification channel"
  value       = newrelic_notification_channel.team_email_channel.id
}

output "workflow_id" {
  description = "ID of the workflow"
  value       = newrelic_workflow.team_workflow.id
}

output "condition_high_error_rate_entity_guid" {
  description = "Entity GUID of the high error rate condition"
  value       = newrelic_nrql_alert_condition.high_error_rate.entity_guid
}

output "condition_high_latency_entity_guid" {
  description = "Entity GUID of the high latency condition"
  value       = newrelic_nrql_alert_condition.high_latency.entity_guid
}

output "muting_rule_id" {
  description = "ID of the muting rule (empty string if create_muting_rule = false)"
  value       = var.create_muting_rule ? newrelic_alert_muting_rule.team_maintenance[0].id : ""
}

output "team" {
  description = "Team name — pass as NR_TEAM to nr_tag_resources.py"
  value       = var.team
}
