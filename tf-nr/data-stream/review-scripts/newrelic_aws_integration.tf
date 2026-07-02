# ============================================================
# New Relic + AWS Integration via Kinesis Firehose (Metric Streams)
# ============================================================
# Rewritten to match the OFFICIAL New Relic example module:
# https://github.com/newrelic/terraform-provider-newrelic/blob/main/examples/modules/cloud-integrations/aws/main.tf
#
# Verified against:
#   - newrelic_cloud_aws_link_account     (registry.terraform.io/providers/newrelic/newrelic/latest/docs/resources/cloud_aws_link_account)
#   - newrelic_cloud_aws_integrations     (registry.terraform.io/providers/newrelic/newrelic/latest/docs/resources/cloud_aws_integrations)
#   - newrelic_api_access_key             (registry.terraform.io/providers/newrelic/newrelic/latest/docs/resources/api_access_key)
#
# A hardened S3 module ships alongside this file at ./modules/s3
# (KMS encryption, versioning, public access block, TLS-only +
# encryption-enforced bucket policy, lifecycle expiration). The
# Firehose backup bucket below uses it directly.
#
# ACTION REQUIRED BEFORE GOV REVIEW:
#   1. If your org has an existing S3 module, diff it against
#      ./modules/s3 and decide which to standardize on (see note
#      at the "firehose_backup_bucket" module block below).
#   2. Confirm var.newrelic_account_region (US vs EU data center).
#   3. Decide PUSH vs PULL (see note above the link_account resources).
#   4. Have your security team review the IAM scope — the New Relic
#      linking role uses AWS-managed ReadOnlyAccess plus a small inline
#      policy for the extras New Relic requires (config, elasticache,
#      tag:GetResources, budgets). This matches New Relic's documented
#      console flow.
#   5. Neither this file nor ./modules/s3 has been run through
#      `terraform validate` — no Terraform binary / network access in
#      this environment. Run init/validate/plan yourself before review.
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
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }
}

# ============================================================
# Variables
# ============================================================

variable "name" {
  description = "Identifier used to name/tag all resources for this integration (e.g. \"prod\", \"shared-services\")"
  type        = string
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "newrelic_account_id" {
  description = "Your New Relic account ID. This value is ALSO used as the External ID in the IAM trust policy — this is correct per New Relic's design, not a placeholder to swap out."
  type        = string
}

variable "newrelic_account_region" {
  description = "New Relic data center for this account: \"US\" or \"EU\""
  type        = string
  default     = "US"

  validation {
    condition     = contains(["US", "EU"], var.newrelic_account_region)
    error_message = "newrelic_account_region must be \"US\" or \"EU\"."
  }
}

variable "newrelic_api_key" {
  description = "New Relic User API key (NRAK-...), used only for Terraform provider auth. Store in a secrets manager / CI secret store, not in tfvars committed to source control."
  type        = string
  sensitive   = true
}

variable "metric_collection_mode" {
  description = "PUSH = CloudWatch Metric Streams via Firehose (recommended, lower latency, lower cost at scale). PULL = API polling."
  type        = string
  default     = "PUSH"

  validation {
    condition     = contains(["PUSH", "PULL"], var.metric_collection_mode)
    error_message = "metric_collection_mode must be \"PUSH\" or \"PULL\"."
  }
}

variable "output_format" {
  description = "CloudWatch Metric Stream output format. New Relic's console setup doc specifies 'opentelemetry0.7' (this is the default here to match that flow). 'opentelemetry1.0' is also supported by New Relic (newer binary protobuf format, richer metadata) and can be selected if you deliberately want it. JSON is NOT supported."
  type        = string
  default     = "opentelemetry0.7"

  validation {
    condition     = contains(["opentelemetry0.7", "opentelemetry1.0"], var.output_format)
    error_message = "output_format must be opentelemetry0.7 (per New Relic's console doc) or opentelemetry1.0. JSON is not supported."
  }
}

variable "include_metric_filters" {
  description = "Map of namespace => metric names to INCLUDE in the metric stream. Leave empty to stream all namespaces."
  type        = map(list(string))
  default     = {}
}

variable "exclude_metric_filters" {
  description = "Map of namespace => metric names to EXCLUDE from the metric stream."
  type        = map(list(string))
  default     = {}
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
  region     = var.newrelic_account_region
}

# ============================================================
# STEP 1: IAM Role for New Relic — trust policy with External ID
# ============================================================
# New Relic's AWS account ID (754728514883) is fixed and documented
# publicly by New Relic; it does not change per customer.
# The External ID is your own New Relic account_id — New Relic's
# provider and console both use this convention, there is no separate
# "external id" value to fetch from an API.

data "aws_iam_policy_document" "newrelic_assume_policy" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "AWS"
      identifiers = ["754728514883"]
    }

    condition {
      test     = "StringEquals"
      variable = "sts:ExternalId"
      values   = [var.newrelic_account_id]
    }
  }
}

resource "aws_iam_role" "newrelic_aws_role" {
  name        = "NewRelicInfrastructure-Integrations-${var.name}"
  description = "Role assumed by New Relic to read AWS account data for monitoring/integrations"

  assume_role_policy = data.aws_iam_policy_document.newrelic_assume_policy.json
}

# ============================================================
# STEP 2 & 3: Linking-role permissions
# ============================================================
# Matches the New Relic console/docs flow exactly: attach the AWS-managed
# ReadOnlyAccess policy, PLUS a small inline policy for the extra actions
# New Relic requires that ReadOnlyAccess does not grant.
#
# The four extras from New Relic's "set minimum permissions" step:
#   config:BatchGetResourceConfig, config:ListDiscoveredResources,
#   elasticache:DescribeCacheClusters, tag:GetResources
# (config:* and tag:GetResources are actually covered by ReadOnlyAccess,
#  but New Relic lists them explicitly, so we include them for parity and
#  in case ReadOnlyAccess scope changes.)
#
# We also keep budgets:ViewBudget for the budgets integration you asked
# for; ReadOnlyAccess does not include Budgets view.

# 2a. AWS-managed ReadOnlyAccess (the "read only" role the docs mean).
resource "aws_iam_role_policy_attachment" "newrelic_readonly" {
  role       = aws_iam_role.newrelic_aws_role.name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}

# 2b. Inline policy for the extras New Relic calls out explicitly.
resource "aws_iam_role_policy" "newrelic_extra_permissions" {
  name = "NewRelicCloudIntegrationsExtras-${var.name}"
  role = aws_iam_role.newrelic_aws_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "config:BatchGetResourceConfig",
          "config:ListDiscoveredResources",
          "elasticache:DescribeCacheClusters",
          "tag:GetResources",
          "budgets:ViewBudget"
        ]
        Resource = "*"
      }
    ]
  })
}

# ============================================================
# STEP 4: S3 bucket for Firehose backup (failed deliveries)
# ============================================================
# Uses the hardened ./modules/s3 module shipped alongside this file:
# KMS encryption (customer-managed key, auto-rotated), versioning,
# full public access block, TLS-only + encryption-enforced bucket
# policy, and lifecycle expiration.
#
# >>> If your org has its own established S3 module, swap the
# >>> `source` below to point at it and compare the two side by side
# >>> before deciding which to use for gov review.

module "firehose_backup_bucket" {
  source = "./modules/s3"

  bucket_name   = "newrelic-aws-bucket-${var.name}-${random_string.s3_suffix.id}"
  force_destroy = false # set true only in non-prod / throwaway envs

  enable_versioning = true
  sse_algorithm     = "aws:kms" # module creates and rotates its own CMK by default

  enable_lifecycle_rule                        = true
  lifecycle_expiration_days                    = 30
  lifecycle_noncurrent_version_expiration_days = 30

  # Documents in the bucket policy itself that the Firehose role may
  # write here, in addition to the IAM identity policy on that role.
  additional_principals_allowed = [aws_iam_role.firehose_newrelic_role.arn]

  tags = {
    Purpose   = "newrelic-firehose-backup"
    ManagedBy = "terraform"
    Stack     = var.name
  }
}

resource "random_string" "s3_suffix" {
  length  = 8
  special = false
  upper   = false
}

# ============================================================
# STEP 5: Firehose delivery role + stream
# ============================================================

resource "aws_iam_role" "firehose_newrelic_role" {
  name = "firehose_newrelic_role_${var.name}"

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

resource "aws_iam_role_policy" "firehose_newrelic_policy" {
  name = "firehose-s3-backup-${var.name}"
  role = aws_iam_role.firehose_newrelic_role.id

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
          module.firehose_backup_bucket.arn,
          "${module.firehose_backup_bucket.arn}/*"
        ]
      },
      {
        # Required so Firehose can write delivery errors to CloudWatch Logs.
        Effect = "Allow"
        Action = [
          "logs:PutLogEvents"
        ]
        Resource = [
          "${aws_cloudwatch_log_group.firehose.arn}:*"
        ]
      },
      {
        # If the S3 backup bucket uses a customer-managed KMS key, Firehose
        # must be able to use it to encrypt the objects it writes.
        Effect = "Allow"
        Action = [
          "kms:GenerateDataKey",
          "kms:Decrypt"
        ]
        Resource = "*"
        Condition = {
          StringEquals = {
            "kms:ViaService" = "s3.${var.aws_region}.amazonaws.com"
          }
        }
      }
    ]
  })
}

locals {
  newrelic_urls = {
    US = "https://aws-api.newrelic.com/cloudwatch-metrics/v1"
    EU = "https://aws-api.eu01.nr-data.net/cloudwatch-metrics/v1"
  }
}

# ------------------------------------------------------------
# CloudWatch logging for the Firehose (CRITICAL for diagnosis)
# ------------------------------------------------------------
# Without this, a 403 (bad license key) or any delivery failure is
# invisible except by decoding S3 backup objects by hand. With it,
# `aws logs tail` shows New Relic's actual HTTP response.

resource "aws_cloudwatch_log_group" "firehose" {
  name              = "/aws/kinesisfirehose/newrelic_firehose_stream_${var.name}"
  retention_in_days = 14
}

resource "aws_cloudwatch_log_stream" "firehose_http" {
  name           = "HttpEndpointDelivery"
  log_group_name = aws_cloudwatch_log_group.firehose.name
}

resource "aws_cloudwatch_log_stream" "firehose_s3" {
  name           = "S3Delivery"
  log_group_name = aws_cloudwatch_log_group.firehose.name
}

# Customer-managed ingest key, created and rotated via Terraform —
# NOT a static license key pasted into a variable.
resource "newrelic_api_access_key" "newrelic_aws_access_key" {
  account_id  = var.newrelic_account_id
  key_type    = "INGEST"
  ingest_type = "LICENSE"
  name        = "Metric Stream Key for ${var.name}"
  notes       = "AWS Cloud Integrations Metric Stream Key (managed by Terraform)"
}

resource "aws_kinesis_firehose_delivery_stream" "newrelic_firehose_stream" {
  name        = "newrelic_firehose_stream_${var.name}"
  destination = "http_endpoint"

  http_endpoint_configuration {
    url                = local.newrelic_urls[var.newrelic_account_region]
    name               = "New Relic ${var.name}"
    access_key         = newrelic_api_access_key.newrelic_aws_access_key.key
    buffering_size     = 1
    buffering_interval = 60
    role_arn           = aws_iam_role.firehose_newrelic_role.arn
    s3_backup_mode     = "FailedDataOnly"
    retry_duration     = 60

    # New Relic's metric endpoint requires GZIP-encoded requests.
    request_configuration {
      content_encoding = "GZIP"
    }

    # Surface delivery errors (403 bad key, etc.) into CloudWatch Logs.
    cloudwatch_logging_options {
      enabled         = true
      log_group_name  = aws_cloudwatch_log_group.firehose.name
      log_stream_name = aws_cloudwatch_log_stream.firehose_http.name
    }

    s3_configuration {
      role_arn           = aws_iam_role.firehose_newrelic_role.arn
      bucket_arn         = module.firehose_backup_bucket.arn
      buffering_size     = 10
      buffering_interval = 400
      compression_format = "GZIP"

      cloudwatch_logging_options {
        enabled         = true
        log_group_name  = aws_cloudwatch_log_group.firehose.name
        log_stream_name = aws_cloudwatch_log_stream.firehose_s3.name
      }
    }
  }

  # Make sure the ingest key and log streams exist before the stream
  # tries to use them (avoids a race that can surface as a 403).
  depends_on = [
    newrelic_api_access_key.newrelic_aws_access_key,
    aws_cloudwatch_log_stream.firehose_http,
    aws_cloudwatch_log_stream.firehose_s3,
  ]
}

# ============================================================
# STEP 6: CloudWatch Metric Stream → Firehose
# ============================================================
# Dedicated role for the CloudWatch Metric Stream service principal —
# this is REQUIRED; it cannot reuse the Firehose delivery role.

resource "aws_iam_role" "metric_stream_to_firehose" {
  name = "newrelic_metric_stream_to_firehose_role_${var.name}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "streams.metrics.cloudwatch.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })
}

resource "aws_iam_role_policy" "metric_stream_to_firehose" {
  name = "default"
  role = aws_iam_role.metric_stream_to_firehose.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "firehose:PutRecord",
          "firehose:PutRecordBatch"
        ]
        Resource = aws_kinesis_firehose_delivery_stream.newrelic_firehose_stream.arn
      }
    ]
  })
}

resource "aws_cloudwatch_metric_stream" "newrelic_metric_stream" {
  name          = "newrelic-metric-stream-${var.name}"
  role_arn      = aws_iam_role.metric_stream_to_firehose.arn
  firehose_arn  = aws_kinesis_firehose_delivery_stream.newrelic_firehose_stream.arn
  output_format = var.output_format

  dynamic "exclude_filter" {
    for_each = var.exclude_metric_filters
    content {
      namespace    = exclude_filter.key
      metric_names = exclude_filter.value
    }
  }

  dynamic "include_filter" {
    for_each = var.include_metric_filters
    content {
      namespace    = include_filter.key
      metric_names = include_filter.value
    }
  }
}

# ============================================================
# STEP 7: New Relic account linking (the GUI step, automated)
# ============================================================
# This IS the "enroll the ARN" step from the New Relic GUI.

resource "newrelic_cloud_aws_link_account" "newrelic_cloud_integration" {
  account_id              = var.newrelic_account_id
  arn                     = aws_iam_role.newrelic_aws_role.arn
  metric_collection_mode  = var.metric_collection_mode
  name                    = "${var.name} ${var.metric_collection_mode == "PUSH" ? "metric stream" : "pull"}"

  depends_on = [
    aws_iam_role_policy_attachment.newrelic_readonly,
    aws_iam_role_policy.newrelic_extra_permissions,
  ]
}

# Polling-based integrations for services without metric-stream support
# (Billing, CloudTrail, Health, Trusted Advisor, VPC, X-Ray). These run
# regardless of PUSH/PULL mode for metrics, per New Relic's guidance.
resource "newrelic_cloud_aws_integrations" "newrelic_cloud_integration" {
  account_id        = var.newrelic_account_id
  linked_account_id = newrelic_cloud_aws_link_account.newrelic_cloud_integration.id

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
  description = "ARN of the IAM role enrolled with New Relic"
  value       = aws_iam_role.newrelic_aws_role.arn
}

output "newrelic_linked_account_id" {
  description = "New Relic's internal ID for the linked AWS account"
  value       = newrelic_cloud_aws_link_account.newrelic_cloud_integration.id
}

output "firehose_stream_arn" {
  value = aws_kinesis_firehose_delivery_stream.newrelic_firehose_stream.arn
}

output "cloudwatch_metric_stream_arn" {
  value = aws_cloudwatch_metric_stream.newrelic_metric_stream.arn
}

output "firehose_backup_bucket_arn" {
  value = module.firehose_backup_bucket.arn
}
