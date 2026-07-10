# Verified against New Relic's documentation for the CloudWatch Metric
# Streams integration. Note this is a different path than New Relic's
# generic log-ingest Firehose endpoint -- using the wrong one is a real way
# to get "delivery succeeds, nothing shows up in New Relic."
locals {
  newrelic_metric_stream_urls = {
    US = "https://aws-api.newrelic.com/cloudwatch-metrics/v1"
    EU = "https://aws-api.eu01.nr-data.net/cloudwatch-metrics/v1"
  }

  # New Relic's documented FedRAMP endpoint for AWS Metric Streams ingest.
  # There is only one govcloud URL published (no separate EU-gov variant).
  newrelic_govcloud_metric_stream_url = "https://gov-aws-api.newrelic.com/cloudwatch-metrics/v1"

  newrelic_endpoint_url = (
    var.newrelic_endpoint_variant == "govcloud"
    ? local.newrelic_govcloud_metric_stream_url
    : local.newrelic_metric_stream_urls[var.newrelic_account_region]
  )
}
