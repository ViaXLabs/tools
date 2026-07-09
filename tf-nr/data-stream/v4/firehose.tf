# Forces Terraform to wait after IAM/KMS resources are applied before
# creating the delivery stream. depends_on alone only guarantees ORDER of
# apply, not that AWS has finished propagating the policy internally -
# that's what caused streams created fresh (destroy + recreate) to fail
# silently while in-place updates to an existing stream worked fine.
resource "time_sleep" "wait_for_iam_propagation" {
  depends_on = [
    aws_iam_role_policy.firehose_kms,
    aws_iam_role_policy.firehose_s3,
    aws_iam_role_policy.firehose_logs,
  ]

  create_duration = var.kms_propagation_wait
}

resource "aws_kinesis_firehose_delivery_stream" "to_newrelic" {
  name        = "${var.name_prefix}-stream"
  destination = "http_endpoint"

  server_side_encryption {
    enabled  = true
    key_type = "CUSTOMER_MANAGED_CMK"
    key_arn  = aws_kms_key.firehose.arn
  }

  http_endpoint_configuration {
    url            = local.newrelic_endpoint_url
    name           = "New Relic"
    access_key     = newrelic_api_access_key.newrelic_aws_access_key.key
    role_arn       = aws_iam_role.firehose.arn
    s3_backup_mode = "FailedDataOnly"

    buffering_size     = 1  # MB
    buffering_interval = 60 # seconds -- kept low since this feeds a near-real-time CloudWatch Metric Stream

    retry_duration = 300

    request_configuration {
      content_encoding = "GZIP"
    }

    cloudwatch_logging_options {
      enabled         = true
      log_group_name  = aws_cloudwatch_log_group.firehose.name
      log_stream_name = aws_cloudwatch_log_stream.destination_delivery.name
    }

    s3_configuration {
      role_arn           = aws_iam_role.firehose.arn
      bucket_arn         = module.backup_bucket.s3_bucket_arn
      buffering_size     = 10
      buffering_interval = 400
      compression_format = "GZIP"

      cloudwatch_logging_options {
        enabled         = true
        log_group_name  = aws_cloudwatch_log_group.firehose.name
        log_stream_name = aws_cloudwatch_log_stream.backup_delivery.name
      }
    }
  }

  tags = var.tags

  # The critical bit: don't even start creating the stream until IAM/KMS
  # have had time to settle. Without this, destroy+recreate cycles are
  # exactly where the race condition bites.
  depends_on = [
    time_sleep.wait_for_iam_propagation,
    aws_kms_key.firehose,
    module.backup_bucket,
  ]
}
