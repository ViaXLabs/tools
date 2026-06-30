output "id" {
  description = "Bucket name (ID)"
  value       = aws_s3_bucket.this.id
}

output "arn" {
  description = "Bucket ARN"
  value       = aws_s3_bucket.this.arn
}

output "bucket_domain_name" {
  value = aws_s3_bucket.this.bucket_domain_name
}

output "kms_key_arn" {
  description = "ARN of the KMS key used for encryption (module-created or supplied), null if using AES256"
  value       = local.kms_key_arn
}

output "kms_key_id" {
  description = "Key ID of the module-created KMS key, if one was created"
  value       = local.create_kms_key ? aws_kms_key.this[0].key_id : null
}
