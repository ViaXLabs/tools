variable "bucket_name" {
  description = "Name of the S3 bucket. Must be globally unique."
  type        = string
}

variable "force_destroy" {
  description = "Allow Terraform to destroy the bucket even if it contains objects. Set false for anything long-lived/production."
  type        = bool
  default     = false
}

variable "enable_versioning" {
  description = "Enable S3 object versioning (recommended for audit trail and accidental-delete protection)."
  type        = bool
  default     = true
}

variable "sse_algorithm" {
  description = "Server-side encryption algorithm: \"aws:kms\" (recommended, customer-managed key) or \"AES256\" (SSE-S3, AWS-managed key)."
  type        = string
  default     = "aws:kms"

  validation {
    condition     = contains(["aws:kms", "AES256"], var.sse_algorithm)
    error_message = "sse_algorithm must be \"aws:kms\" or \"AES256\"."
  }
}

variable "kms_key_arn" {
  description = "ARN of an existing customer-managed KMS key to use for bucket encryption. If null and sse_algorithm is \"aws:kms\", a new key is created by this module."
  type        = string
  default     = null
}

variable "kms_key_deletion_window_in_days" {
  description = "Waiting period before a module-created KMS key is deleted, if it is ever destroyed."
  type        = number
  default     = 30
}

variable "block_public_access" {
  description = "Block all forms of public access to the bucket. Should be true for virtually all use cases, including Firehose backup buckets."
  type        = bool
  default     = true
}

variable "enforce_tls" {
  description = "Add a bucket policy statement that denies any request made without TLS (aws:SecureTransport)."
  type        = bool
  default     = true
}

variable "enable_lifecycle_rule" {
  description = "Enable a lifecycle rule that expires objects and noncurrent versions after a retention period."
  type        = bool
  default     = true
}

variable "lifecycle_expiration_days" {
  description = "Days after which current object versions expire (only used if enable_lifecycle_rule is true)."
  type        = number
  default     = 30
}

variable "lifecycle_noncurrent_version_expiration_days" {
  description = "Days after which noncurrent object versions are permanently deleted (only used if enable_lifecycle_rule and enable_versioning are true)."
  type        = number
  default     = 30
}

variable "enable_access_logging" {
  description = "Enable S3 server access logging to a separate logging bucket."
  type        = bool
  default     = false
}

variable "logging_bucket_id" {
  description = "Bucket ID (name) to deliver access logs to. Required if enable_access_logging is true. Must already exist (typically a dedicated, central log bucket)."
  type        = string
  default     = null
}

variable "logging_prefix" {
  description = "Key prefix for delivered access log objects."
  type        = string
  default     = "s3-access-logs/"
}

variable "additional_principals_allowed" {
  description = "Optional list of IAM principal ARNs to explicitly allow in the bucket policy (e.g. a Firehose delivery role). Leave empty if access is granted entirely via IAM policies attached to roles instead."
  type        = list(string)
  default     = []
}

variable "tags" {
  description = "Tags applied to all resources created by this module."
  type        = map(string)
  default     = {}
}
