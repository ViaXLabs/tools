# Verified against New Relic's documentation for the CloudWatch Metric
# Streams integration. Note this is a different path than New Relic's
# generic log-ingest Firehose endpoint -- using the wrong one is a real way
# to get "delivery succeeds, nothing shows up in New Relic."
locals {
  newrelic_metric_stream_urls = {
    US = "https://aws-api.newrelic.com/cloudwatch-metrics/v1"
    EU = "https://aws-api.eu01.nr-data.net/cloudwatch-metrics/v1"
  }

  newrelic_endpoint_url = local.newrelic_metric_stream_urls[var.newrelic_account_region]
}
