# A dedicated log group for this stream only, with separate streams for the
# primary (New Relic) destination vs. the S3 backup path. This is what keeps
# the error log readable - mixing multiple streams' errors into one shared
# log group is the usual cause of "the log is a mess."

resource "aws_cloudwatch_log_group" "firehose" {
  name              = "/aws/kinesisfirehose/${var.name_prefix}"
  retention_in_days = 30

  tags = var.tags
}

resource "aws_cloudwatch_log_stream" "destination_delivery" {
  name           = "DestinationDelivery"
  log_group_name = aws_cloudwatch_log_group.firehose.name
}

resource "aws_cloudwatch_log_stream" "backup_delivery" {
  name           = "BackupDelivery"
  log_group_name = aws_cloudwatch_log_group.firehose.name
}
