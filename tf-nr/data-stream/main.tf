# ============================================================
# Hardened S3 bucket module
# Encryption (KMS by default) · Versioning · Public access block
# TLS-only bucket policy · Lifecycle expiration · Optional access logging
# ============================================================

locals {
  create_kms_key = var.sse_algorithm == "aws:kms" && var.kms_key_arn == null
  kms_key_arn    = var.sse_algorithm == "aws:kms" ? (var.kms_key_arn != null ? var.kms_key_arn : aws_kms_key.this[0].arn) : null
}

# ------------------------------------------------------------
# Optional customer-managed KMS key (created only if one wasn't supplied)
# ------------------------------------------------------------

resource "aws_kms_key" "this" {
  count = local.create_kms_key ? 1 : 0

  description             = "CMK for S3 bucket ${var.bucket_name}"
  deletion_window_in_days = var.kms_key_deletion_window_in_days
  enable_key_rotation     = true

  tags = var.tags
}

resource "aws_kms_alias" "this" {
  count = local.create_kms_key ? 1 : 0

  name          = "alias/s3-${var.bucket_name}"
  target_key_id = aws_kms_key.this[0].key_id
}

# ------------------------------------------------------------
# Bucket
# ------------------------------------------------------------

resource "aws_s3_bucket" "this" {
  bucket        = var.bucket_name
  force_destroy = var.force_destroy

  tags = var.tags
}

resource "aws_s3_bucket_ownership_controls" "this" {
  bucket = aws_s3_bucket.this.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_versioning" "this" {
  bucket = aws_s3_bucket.this.id

  versioning_configuration {
    status = var.enable_versioning ? "Enabled" : "Suspended"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  bucket = aws_s3_bucket.this.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = var.sse_algorithm
      kms_master_key_id = var.sse_algorithm == "aws:kms" ? local.kms_key_arn : null
    }
    bucket_key_enabled = var.sse_algorithm == "aws:kms" ? true : null
  }
}

resource "aws_s3_bucket_public_access_block" "this" {
  count = var.block_public_access ? 1 : 0

  bucket = aws_s3_bucket.this.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ------------------------------------------------------------
# Lifecycle: expire current + noncurrent versions after retention period
# ------------------------------------------------------------

resource "aws_s3_bucket_lifecycle_configuration" "this" {
  count = var.enable_lifecycle_rule ? 1 : 0

  bucket = aws_s3_bucket.this.id

  rule {
    id     = "expire-objects"
    status = "Enabled"

    filter {}

    expiration {
      days = var.lifecycle_expiration_days
    }

    dynamic "noncurrent_version_expiration" {
      for_each = var.enable_versioning ? [1] : []
      content {
        noncurrent_days = var.lifecycle_noncurrent_version_expiration_days
      }
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

# ------------------------------------------------------------
# Optional server access logging to a separate logging bucket
# ------------------------------------------------------------

resource "aws_s3_bucket_logging" "this" {
  count = var.enable_access_logging ? 1 : 0

  bucket = aws_s3_bucket.this.id

  target_bucket = var.logging_bucket_id
  target_prefix = var.logging_prefix
}

# ------------------------------------------------------------
# Bucket policy: deny non-TLS requests, deny unencrypted uploads,
# and (optionally) allow specific principals
# ------------------------------------------------------------

data "aws_iam_policy_document" "this" {
  # Deny any request not made over TLS
  dynamic "statement" {
    for_each = var.enforce_tls ? [1] : []
    content {
      sid       = "DenyInsecureTransport"
      effect    = "Deny"
      actions   = ["s3:*"]
      resources = [
        aws_s3_bucket.this.arn,
        "${aws_s3_bucket.this.arn}/*"
      ]

      principals {
        type        = "*"
        identifiers = ["*"]
      }

      condition {
        test     = "Bool"
        variable = "aws:SecureTransport"
        values   = ["false"]
      }
    }
  }

  # Deny PutObject calls that don't request server-side encryption
  statement {
    sid       = "DenyUnencryptedObjectUploads"
    effect    = "Deny"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.this.arn}/*"]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    condition {
      test     = "StringNotEquals"
      variable = "s3:x-amz-server-side-encryption"
      values   = var.sse_algorithm == "aws:kms" ? ["aws:kms"] : ["AES256"]
    }
  }

  # Optional explicit allow for specific principals (e.g. a Firehose role),
  # useful when you want the policy itself to document who can write here,
  # in addition to / instead of relying solely on IAM identity policies.
  dynamic "statement" {
    for_each = length(var.additional_principals_allowed) > 0 ? [1] : []
    content {
      sid     = "AllowExplicitPrincipals"
      effect  = "Allow"
      actions = [
        "s3:GetObject",
        "s3:PutObject",
        "s3:ListBucket",
        "s3:GetBucketLocation"
      ]
      resources = [
        aws_s3_bucket.this.arn,
        "${aws_s3_bucket.this.arn}/*"
      ]

      principals {
        type        = "AWS"
        identifiers = var.additional_principals_allowed
      }
    }
  }
}

resource "aws_s3_bucket_policy" "this" {
  bucket = aws_s3_bucket.this.id
  policy = data.aws_iam_policy_document.this.json

  depends_on = [aws_s3_bucket_public_access_block.this]
}
