# ============================================================
# CloudWatch Metric Stream -> Firehose
# ============================================================
# This is what actually populates the Firehose stream (firehose.tf) with
# data. Without this resource, the Firehose exists and can reach New Relic,
# but nothing feeds it automatically. Requires its own IAM role -- it
# cannot reuse the Firehose delivery role from iam.tf, since the two are
# assumed by different service principals.

resource "aws_iam_role" "metric_stream_to_firehose" {
  name = "${var.name_prefix}-metric-stream-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "streams.metrics.cloudwatch.amazonaws.com" }
      Action    = "sts:AssumeRole"
      Condition = {
        StringEquals = {
          "aws:SourceAccount" = data.aws_caller_identity.current.account_id
        }
      }
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy" "metric_stream_to_firehose" {
  name = "firehose-put-record"
  role = aws_iam_role.metric_stream_to_firehose.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "firehose:PutRecord",
        "firehose:PutRecordBatch"
      ]
      Resource = aws_kinesis_firehose_delivery_stream.to_newrelic.arn
    }]
  })
}

# Same IAM-propagation concern as the Firehose/KMS pairing in firehose.tf --
# don't let the metric stream try to use the role before AWS has finished
# propagating the policy.
resource "time_sleep" "wait_for_metric_stream_iam" {
  depends_on      = [aws_iam_role_policy.metric_stream_to_firehose]
  create_duration = "30s"
}

resource "aws_cloudwatch_metric_stream" "this" {
  name          = "${var.name_prefix}-metric-stream"
  role_arn      = aws_iam_role.metric_stream_to_firehose.arn
  firehose_arn  = aws_kinesis_firehose_delivery_stream.to_newrelic.arn
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

  tags = var.tags

  depends_on = [time_sleep.wait_for_metric_stream_iam]
}
