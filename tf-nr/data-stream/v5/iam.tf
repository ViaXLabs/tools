resource "aws_iam_role" "firehose" {
  name = "${var.name_prefix}-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "firehose.amazonaws.com" }
      Action    = "sts:AssumeRole"
      Condition = {
        StringEquals = {
          # Confused-deputy protection: only let Firehose assume this role
          # for resources created in *this* account. (Not sts:ExternalId -
          # that condition key is for cross-account third parties, and
          # Firehose never passes one, so using it here would silently
          # break every AssumeRole call.)
          "aws:SourceAccount" = data.aws_caller_identity.current.account_id
        }
      }
    }]
  })

  tags = var.tags
}

# --- KMS access ---
# Mirrors the AllowFirehoseRole statement on the key policy in kms.tf.
# Both sides are required; this is not redundant. Only created when the
# test-matrix toggle has customer-managed KMS enabled.
resource "aws_iam_role_policy" "firehose_kms" {
  count = var.enable_customer_managed_kms ? 1 : 0

  name = "${var.name_prefix}-kms-access"
  role = aws_iam_role.firehose.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "kms:GenerateDataKey",
        "kms:Decrypt",
        "kms:DescribeKey",
        "kms:CreateGrant"
      ]
      Resource = aws_kms_key.firehose[0].arn
    }]
  })
}

# --- S3 backup bucket access ---
resource "aws_iam_role_policy" "firehose_s3" {
  name = "${var.name_prefix}-s3-access"
  role = aws_iam_role.firehose.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "s3:AbortMultipartUpload",
        "s3:GetBucketLocation",
        "s3:GetObject",
        "s3:ListBucket",
        "s3:ListBucketMultipartUploads",
        "s3:PutObject"
      ]
      Resource = [
        module.backup_bucket.s3_bucket_arn,
        "${module.backup_bucket.s3_bucket_arn}/*"
      ]
    }]
  })
}

# --- CloudWatch error logging access ---
resource "aws_iam_role_policy" "firehose_logs" {
  name = "${var.name_prefix}-logs-access"
  role = aws_iam_role.firehose.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "logs:PutLogEvents"
      ]
      Resource = [
        "${aws_cloudwatch_log_group.firehose.arn}:*"
      ]
    }]
  })
}
