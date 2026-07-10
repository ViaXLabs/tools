variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-east-1"
}

variable "name_prefix" {
  description = "Prefix used to name all resources in this stack"
  type        = string
  default     = "newrelic-firehose"
}

variable "newrelic_account_id" {
  description = "Your New Relic account ID. Also used as the External ID in the AWS IAM trust policy for the account-link role -- this is New Relic's documented convention, not a placeholder."
  type        = string
}

variable "newrelic_account_region" {
  description = "New Relic data center for this account: \"US\" or \"EU\". Drives both the newrelic provider region and which Firehose HTTP endpoint URL is used."
  type        = string
  default     = "US"

  validation {
    condition     = contains(["US", "EU"], var.newrelic_account_region)
    error_message = "newrelic_account_region must be \"US\" or \"EU\"."
  }
}

variable "newrelic_provider_api_key" {
  description = "New Relic USER API key (starts with NRAK-...). Used only to authenticate the newrelic Terraform provider itself (create the account link, integrations, and the ingest key resource) -- this is NOT the Firehose ingest/license key. That key is generated automatically by newrelic_api_access_key in newrelic.tf."
  type        = string
  sensitive   = true
}

variable "metric_collection_mode" {
  description = "PUSH = CloudWatch Metric Streams via Firehose (what this stack builds). PULL = API polling. This variable only labels the mode on the New Relic side; changing it to PULL does not remove the metric-stream/Firehose resources below -- do that manually if you want pure PULL."
  type        = string
  default     = "PUSH"

  validation {
    condition     = contains(["PUSH", "PULL"], var.metric_collection_mode)
    error_message = "metric_collection_mode must be \"PUSH\" or \"PULL\"."
  }
}

variable "output_format" {
  description = "CloudWatch Metric Stream output format. New Relic accepts opentelemetry0.7 or opentelemetry1.0 only -- AWS also supports plain \"json\" but New Relic's endpoint does not accept it."
  type        = string
  default     = "opentelemetry0.7"

  validation {
    condition     = contains(["opentelemetry0.7", "opentelemetry1.0"], var.output_format)
    error_message = "output_format must be opentelemetry0.7 or opentelemetry1.0 (New Relic does not accept \"json\")."
  }
}

variable "include_metric_filters" {
  description = "Map of namespace => metric names to INCLUDE in the metric stream. Leave empty to stream all namespaces. Mutually exclusive with exclude_metric_filters."
  type        = map(list(string))
  default     = {}
}

variable "exclude_metric_filters" {
  description = "Map of namespace => metric names to EXCLUDE from the metric stream. Mutually exclusive with include_metric_filters."
  type        = map(list(string))
  default     = {}
}

variable "kms_propagation_wait" {
  description = "How long to wait after IAM/KMS resources are created before creating the Firehose stream, to dodge IAM/KMS eventual-consistency races"
  type        = string
  default     = "45s"
}

variable "tags" {
  description = "Common tags applied to all resources"
  type        = map(string)
  default = {
    ManagedBy = "terraform"
    Project   = "newrelic-firehose"
  }
}

# ============================================================
# Test-matrix toggles
# ============================================================
# Flip these and re-apply to isolate which dimension (KMS, S3 backup
# volume, or commercial-vs-govcloud endpoint) is actually responsible for
# the stall, instead of hand-editing files for each combination.

variable "enable_customer_managed_kms" {
  description = "true = CUSTOMER_MANAGED_CMK on the Firehose stream + KMS-encrypted S3 backup bucket (the hardened config). false = AWS_OWNED_CMK on the stream + plain SSE-S3 (AES256) on the bucket -- i.e. the original no-KMS baseline that was known to work, with everything else identical (IAM, CloudWatch logging, metric stream) so KMS is the only variable that changed."
  type        = bool
  default     = true
}

variable "s3_backup_mode" {
  description = "FailedDataOnly = only records that fail HTTP delivery land in S3 (production default). AllData = every record Firehose receives also lands in S3, regardless of HTTP delivery outcome -- use this temporarily to prove records are reaching Firehose at all, independent of whatever is happening with KMS or the New Relic endpoint."
  type        = string
  default     = "FailedDataOnly"

  validation {
    condition     = contains(["FailedDataOnly", "AllData"], var.s3_backup_mode)
    error_message = "s3_backup_mode must be \"FailedDataOnly\" or \"AllData\"."
  }
}

variable "newrelic_endpoint_variant" {
  description = "\"commercial\" = aws-api.newrelic.com / aws-api.eu01.nr-data.net (standard accounts). \"govcloud\" = gov-aws-api.newrelic.com -- New Relic's documented FedRAMP endpoint specifically for AWS Metric Streams ingest. Note: this only affects the Firehose destination URL. The newrelic_cloud_aws_link_account / newrelic_cloud_aws_integrations resources in newrelic.tf have NO .gov equivalent in the New Relic provider today -- cloud integrations are out of scope for FedRAMP per New Relic's own documentation. Confirm with your NR account rep whether that part of the stack applies to your account before assuming it needs to move too."
  type        = string
  default     = "commercial"

  validation {
    condition     = contains(["commercial", "govcloud"], var.newrelic_endpoint_variant)
    error_message = "newrelic_endpoint_variant must be \"commercial\" or \"govcloud\"."
  }
}
