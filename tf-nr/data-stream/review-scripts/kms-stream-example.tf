Good — tracked down real provider docs and GitHub-confirmed examples (not just memory) at hashicorp/terraform-provider-aws, and I found one real gap in what I gave you earlier: **`kms:CreateGrant` is required** on the KMS key policy for `CUSTOMER_MANAGED_CMK`, in addition to `GenerateDataKey`/`Decrypt`. AWS's own Firehose data-protection docs are explicit about this — Firehose invokes the KMS CreateGrant operation to create a grant allowing it to use the customer-managed key for encryption and decryption when you set KeyType to CUSTOMER_MANAGED_CMK. If your role only had Decrypt/GenerateDataKey, that alone would explain the failure that made you rip KMS out.

Everything else below is checked against the provider's actual `.markdown` source and multiple working GitHub examples, not recalled from memory.

```hcl
# --- KMS key ---
resource "aws_kms_key" "firehose" {
  description             = "Firehose SSE key for New Relic stream"
  deletion_window_in_days = 7

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "EnableRootAccount"
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
          "kms:CreateGrant"   # <-- required for CUSTOMER_MANAGED_CMK, easy to miss
        ]
        Resource = "*"
      }
    ]
  })
}

data "aws_caller_identity" "current" {}

# --- Matching IAM permissions on the Firehose role ---
resource "aws_iam_role_policy" "firehose_kms" {
  name = "firehose-kms-access"
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
      Resource = aws_kms_key.firehose.arn
    }]
  })
}

# --- The delivery stream ---
resource "aws_kinesis_firehose_delivery_stream" "to_newrelic" {
  name        = "newrelic-stream"
  destination = "http_endpoint"

  server_side_encryption {
    enabled  = true
    key_type = "CUSTOMER_MANAGED_CMK"
    key_arn  = aws_kms_key.firehose.arn
  }

  http_endpoint_configuration {
    url            = "https://aws-api.newrelic.com/firehose/v1"
    name           = "New Relic"
    access_key     = var.newrelic_api_key
    role_arn       = aws_iam_role.firehose.arn
    s3_backup_mode = "FailedDataOnly"

    buffering_size     = 5
    buffering_interval = 300

    s3_configuration {
      role_arn           = aws_iam_role.firehose.arn
      bucket_arn         = aws_s3_bucket.backup.arn
      buffering_size     = 10
      buffering_interval = 400
      compression_format = "GZIP"
    }

    request_configuration {
      content_encoding = "GZIP"
    }
  }
}
```

Two things worth flagging honestly, from what turned up in the search:

1. **`access_key` is not marked `sensitive`** in the provider (there's a long-standing open GitHub issue about it) — your New Relic key will show in plan/state in plaintext. Consider `secret_manager_configuration` instead of `access_key` if that's a concern; I confirmed that's a real, working alternative block (`secret_manager_configuration { secret_arn = ...; role_arn = ... }`), mutually exclusive with `access_key`.
2. A few people have hit "Unsupported block: s3_configuration" nesting errors depending on provider version — if you hit that, it's almost always an old `hashicorp/aws` provider version; the nested form above is what's documented and used in current working examples.

Still can't run `terraform plan` against your actual account from here to catch things like a typo'd ARN or wrong region — that last mile is on you to apply and watch the CloudWatch error logs on the delivery stream if it fails.
