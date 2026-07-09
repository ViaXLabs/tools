data "aws_caller_identity" "current" {}

resource "aws_kms_key" "firehose" {
  description             = "SSE key for ${var.name_prefix} Firehose delivery stream"
  deletion_window_in_days = 7
  enable_key_rotation     = true

  # NOTE: the AllowFirehoseRole statement below is what grants the Firehose
  # role permission to use this key. Both this key policy AND the IAM policy
  # attached to the role (see iam.tf) must independently allow the same
  # actions - Firehose checks both sides. Missing either one is the single
  # most common cause of "SSE enabled but nothing shows up in New Relic."
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "EnableRootAccountFullAccess"
        Effect    = "Allow"
        Principal = { AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root" }
        Action    = "kms:*"
        Resource  = "*"
      },
      {
        Sid       = "AllowFirehoseRole"
        Effect    = "Allow"
        Principal = { AWS = aws_iam_role.firehose.arn }
        Action = [
          "kms:GenerateDataKey",
          "kms:Decrypt",
          "kms:DescribeKey",
          "kms:CreateGrant" # required specifically for CUSTOMER_MANAGED_CMK SSE - easy to miss
        ]
        Resource = "*"
      }
    ]
  })

  tags = merge(var.tags, { Name = "${var.name_prefix}-sse-key" })
}

resource "aws_kms_alias" "firehose" {
  name          = "alias/${var.name_prefix}-firehose"
  target_key_id = aws_kms_key.firehose.key_id
}
