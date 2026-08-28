# MODULE: terraform/modules/common (outputs.tf)
# Consumed by terraform/live/<env>/foundation/outputs.tf, which passes
# db_secret_arn, workload_role_arn, and nexus_pull_secret_arn further
# downstream to the ecs/ and eks/ roots via terraform_remote_state.

output "backup_ecr_repository_urls" {
  description = "Informational only -- nothing downstream reads this, since deploys always pull from Nexus"
  value       = { for k, v in aws_ecr_repository.backup : k => v.repository_url }
}

output "nexus_pull_secret_arn" {
  description = "Passed through so ecs/ and eks/ roots can wire up pull credentials"
  value       = var.nexus_pull_secret_arn
}

output "db_endpoint" {
  value = aws_db_instance.psa.endpoint
}

output "db_secret_arn" {
  value = aws_secretsmanager_secret.db.arn
}

output "db_security_group_id" {
  value = aws_security_group.db.id
}

output "workload_role_arn" {
  value = aws_iam_role.psa_workload.arn
}

output "kms_key_arn" {
  value = aws_kms_key.psa.arn
}
