# ============================================================
# New Relic + AWS Integration via Kinesis Firehose
# ============================================================
# Prerequisites:
#   - terraform-provider-aws
#   - terraform-provider-newrelic
# ============================================================

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    newrelic = {
      source  = "newrelic/newrelic"
      version = "~> 3.0"
    }
  }
}

# ============================================================
# Variables
# ============================================================

variable "aws_region" {
  default = "us-east-1"
}

variable "newrelic_account_id" {
  description = "Your New Relic account ID"
  type        = string
}

variable "newrelic_license_key" {
  description = "Your New Relic ingest license key"
  type        = string
  sensitive   = true
}

variable "newrelic_api_key" {
  description = "Your New Relic User API key (for provider auth)"
  type        = string
  sensitive   = true
}

# ============================================================
# Providers
# ============================================================

provider "aws" {
  region = var.aws_region
}

provider "newrelic" {
  account_id = var.newrelic_account_id
  api_key    = var.newrelic_api_key
  region     = "US" # or "EU"
}

# ============================================================
# DATA: New Relic's AWS account ID (fixed) and external ID
# ============================================================

# New Relic's AWS account ID is always 754728514883
locals {
  newrelic_aws_account_id = "754728514883"
}

# Fetch the external ID New Relic expects for this account
data "newrelic_aws_account_integration_external_id" "this" {
  account_id = var.newrelic_account_id
}

# ============================================================
# STEP 1: IAM Role for New Relic (with External ID)
# ============================================================

resource "aws_iam_role" "newrelic_integration" {
  name        = "NewRelicIntegrationRole"
  description = "Allows New Relic to read AWS metrics and metadata"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${local.newrelic_aws_account_id}:root"
        }
        Action = "sts:AssumeRole"
        Condition = {
          StringEquals = {
            "sts:ExternalId" = data.newrelic_aws_account_integration_external_id.this.external_id
          }
        }
      }
    ]
  })
}

# ============================================================
# STEP 2: Attach ReadOnlyAccess managed policy
# ============================================================

resource "aws_iam_role_policy_attachment" "newrelic_readonly" {
  role       = aws_iam_role.newrelic_integration.name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}

# ============================================================
# STEP 3: Inline policy for Budgets (requires separate perms)
# ============================================================

resource "aws_iam_role_policy" "newrelic_budgets" {
  name = "NewRelicBudgetsPolicy"
  role = aws_iam_role.newrelic_integration.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "budgets:ViewBudget",
          "budgets:DescribeBudgets"
        ]
        Resource = "*"
      }
    ]
  })
}

# ============================================================
# STEP 4: Kinesis Firehose → New Relic
# ============================================================

# S3 bucket for Firehose backup / failed deliveries
resource "aws_s3_bucket" "firehose_backup" {
  bucket        = "newrelic-firehose-backup-${var.newrelic_account_id}"
  force_destroy = true
}

resource "aws_s3_bucket_lifecycle_configuration" "firehose_backup_lifecycle" {
  bucket = aws_s3_bucket.firehose_backup.id
  rule {
    id     = "expire-old-backups"
    status = "Enabled"
    expiration {
      days = 30
    }
    filter {}
  }
}

# IAM role for Firehose to write to S3 and put records
resource "aws_iam_role" "firehose_role" {
  name = "NewRelicFirehoseRole"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "firehose.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })
}

resource "aws_iam_role_policy" "firehose_policy" {
  name = "NewRelicFirehosePolicy"
  role = aws_iam_role.firehose_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
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
          aws_s3_bucket.firehose_backup.arn,
          "${aws_s3_bucket.firehose_backup.arn}/*"
        ]
      }
    ]
  })
}

# Kinesis Firehose delivery stream to New Relic
resource "aws_kinesis_firehose_delivery_stream" "newrelic" {
  name        = "newrelic-metrics-stream"
  destination = "http_endpoint"

  http_endpoint_configuration {
    url                = "https://aws-api.newrelic.com/cloudwatch-metrics/v1"
    name               = "New Relic"
    access_key         = var.newrelic_license_key
    buffering_size     = 1    # MB
    buffering_interval = 60   # seconds
    role_arn           = aws_iam_role.firehose_role.arn
    retry_duration     = 60

    request_configuration {
      content_encoding = "GZIP"
    }

    s3_backup_mode = "FailedDataOnly"
  }

  s3_configuration {
    role_arn           = aws_iam_role.firehose_role.arn
    bucket_arn         = aws_s3_bucket.firehose_backup.arn
    buffering_size     = 5
    buffering_interval = 300
    compression_format = "GZIP"
  }
}

# CloudWatch Metric Stream → Firehose
resource "aws_cloudwatch_metric_stream" "newrelic" {
  name          = "newrelic-metric-stream"
  role_arn      = aws_iam_role.firehose_role.arn
  firehose_arn  = aws_kinesis_firehose_delivery_stream.newrelic.arn
  output_format = "opentelemetry0.7"

  # Optional: scope to specific namespaces. Remove to stream ALL metrics.
  # include_filter {
  #   namespace = "AWS/EC2"
  # }
  # include_filter {
  #   namespace = "AWS/RDS"
  # }
}

# IAM: allow CloudWatch to put records into Firehose
resource "aws_iam_role_policy" "cloudwatch_to_firehose" {
  name = "CloudWatchMetricStreamFirehosePolicy"
  role = aws_iam_role.firehose_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "firehose:PutRecord",
          "firehose:PutRecordBatch"
        ]
        Resource = aws_kinesis_firehose_delivery_stream.newrelic.arn
      }
    ]
  })
}

# ============================================================
# STEP 5: New Relic Account Integration (the final step)
# ============================================================

resource "newrelic_cloud_aws_link_account" "this" {
  name             = "AWS Integration"
  arn              = aws_iam_role.newrelic_integration.arn
  metric_collection_mode = "PUSH" # PUSH = Firehose/Metric Stream; PULL = polling
}

# Wire specific AWS services to poll (used alongside PUSH for non-metric data)
resource "newrelic_cloud_aws_integrations" "this" {
  linked_account_id = newrelic_cloud_aws_link_account.this.id

  billing {}
  cloudtrail {}
  health {}
  trusted_advisor {}
  vpc {}
  x_ray {}
}

# ============================================================
# Outputs
# ============================================================

output "newrelic_integration_role_arn" {
  description = "ARN of the IAM role to enroll in New Relic"
  value       = aws_iam_role.newrelic_integration.arn
}

output "firehose_stream_arn" {
  description = "ARN of the Kinesis Firehose delivery stream"
  value       = aws_kinesis_firehose_delivery_stream.newrelic.arn
}

output "cloudwatch_metric_stream_arn" {
  description = "ARN of the CloudWatch Metric Stream"
  value       = aws_cloudwatch_metric_stream.newrelic.arn
}

output "external_id" {
  description = "New Relic external ID used in the IAM trust policy"
  value       = data.newrelic_aws_account_integration_external_id.this.external_id
}
