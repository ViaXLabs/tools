output "firehose_stream_arn" {
  description = "ARN of the Firehose delivery stream"
  value       = aws_kinesis_firehose_delivery_stream.to_newrelic.arn
}

output "firehose_role_arn" {
  description = "ARN of the IAM role Firehose assumes"
  value       = aws_iam_role.firehose.arn
}

output "kms_key_arn" {
  description = "ARN of the customer-managed KMS key used for SSE"
  value       = aws_kms_key.firehose.arn
}

output "backup_bucket_name" {
  description = "Name of the S3 backup bucket"
  value       = module.backup_bucket.s3_bucket_id
}

output "cloudwatch_log_group" {
  description = "Where to look first when data isn't showing up in New Relic"
  value       = aws_cloudwatch_log_group.firehose.name
}

output "newrelic_integration_role_arn" {
  description = "ARN of the IAM role New Relic assumes to read your AWS account"
  value       = aws_iam_role.newrelic_aws_role.arn
}

output "newrelic_linked_account_id" {
  description = "New Relic's internal ID for this linked AWS account"
  value       = newrelic_cloud_aws_link_account.this.id
}

output "cloudwatch_metric_stream_arn" {
  description = "ARN of the CloudWatch Metric Stream feeding the Firehose"
  value       = aws_cloudwatch_metric_stream.this.arn
}
