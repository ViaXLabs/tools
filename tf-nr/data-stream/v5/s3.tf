# S3 backup bucket using the widely-used community module instead of raw
# aws_s3_bucket resources. Firehose writes here for failed/backup records
# regardless of the primary destination.
#
# Module: https://registry.terraform.io/modules/terraform-aws-modules/s3-bucket/aws

module "backup_bucket" {
  source  = "terraform-aws-modules/s3-bucket/aws"
  version = "~> 5.0"

  bucket_prefix = "${var.name_prefix}-backup-"
  force_destroy = true # convenient in dev/test; remove for production

  control_object_ownership = true
  object_ownership         = "BucketOwnerEnforced"

  block_public_acls      = true
  block_public_policy    = true
  ignore_public_acls     = true
  restrict_public_buckets = true

  versioning = {
    enabled = true
  }

  # Encrypt the backup bucket with the SAME customer-managed key used for
  # the Firehose stream's SSE when the KMS toggle is on. When it's off, this
  # falls back to plain SSE-S3 (AES256) so the "no-KMS" test variant has
  # zero KMS involvement anywhere in the stack, not just on the stream.
  server_side_encryption_configuration = {
    rule = {
      apply_server_side_encryption_by_default = var.enable_customer_managed_kms ? {
        sse_algorithm     = "aws:kms"
        kms_master_key_id = aws_kms_key.firehose[0].arn
        } : {
        sse_algorithm = "AES256"
      }
      bucket_key_enabled = var.enable_customer_managed_kms
    }
  }

  tags = var.tags
}
