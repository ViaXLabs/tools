#!/usr/bin/env bash
#
# verify_metric_streams.sh
#
# Purpose: Confirm, on the AWS side, that RDS, Aurora, and Redshift are
# actually included in the CloudWatch Metric Stream feeding New Relic's
# Firehose. This is the #1 place data silently goes missing -- an
# include-filter that just never had Redshift (or RDS) added to it.
#
# Requires: AWS CLI v2, configured credentials with cloudwatch:List/GetMetricStream
# permissions, in the account/region where the stream lives.
#
# Usage:
#   chmod +x verify_metric_streams.sh
#   ./verify_metric_streams.sh [region]
#
# If no region is passed, uses your default AWS CLI region.

set -euo pipefail

REGION="${1:-$(aws configure get region)}"
if [ -z "$REGION" ]; then
  echo "No region provided and no default region configured. Usage: ./verify_metric_streams.sh <region>"
  exit 1
fi

echo "=================================================================="
echo " CloudWatch Metric Stream Coverage Check -- region: $REGION"
echo "=================================================================="
echo

echo "--- 1. Listing all metric streams in this region ---"
STREAMS=$(aws cloudwatch list-metric-streams --region "$REGION" --output json)
echo "$STREAMS" | jq -r '.Entries[] | "  - \(.Name)  (state: \(.State))  firehose: \(.FirehoseArn)"'
echo

STREAM_NAMES=$(echo "$STREAMS" | jq -r '.Entries[].Name')

if [ -z "$STREAM_NAMES" ]; then
  echo "No metric streams found in $REGION. Either the stream is in a different"
  echo "region, or it hasn't been created yet."
  exit 0
fi

for NAME in $STREAM_NAMES; do
  echo "------------------------------------------------------------------"
  echo " Stream: $NAME"
  echo "------------------------------------------------------------------"

  DETAIL=$(aws cloudwatch get-metric-stream --name "$NAME" --region "$REGION" --output json)

  echo "$DETAIL" | jq '{
    Name, State, OutputFormat,
    IncludeFilters, ExcludeFilters,
    StatisticsConfigurations
  }'

  echo
  echo "  --> Checking for AWS/RDS and AWS/Redshift coverage:"

  HAS_INCLUDE=$(echo "$DETAIL" | jq -e '.IncludeFilters != null and (.IncludeFilters | length > 0)' >/dev/null 2>&1 && echo "yes" || echo "no")
  HAS_EXCLUDE=$(echo "$DETAIL" | jq -e '.ExcludeFilters != null and (.ExcludeFilters | length > 0)' >/dev/null 2>&1 && echo "yes" || echo "no")

  if [ "$HAS_INCLUDE" = "no" ] && [ "$HAS_EXCLUDE" = "no" ]; then
    echo "  No include/exclude filters set -- this stream sends ALL namespaces."
    echo "  RDS, Aurora, and Redshift metrics should all be flowing already."
  fi

  if [ "$HAS_INCLUDE" = "yes" ]; then
    echo "  This stream uses an INCLUDE list. Only namespaces listed below are sent:"
    echo "$DETAIL" | jq -r '.IncludeFilters[].Namespace'
    echo
    RDS_IN=$(echo "$DETAIL" | jq -r '.IncludeFilters[].Namespace' | grep -c '^AWS/RDS$' || true)
    REDSHIFT_IN=$(echo "$DETAIL" | jq -r '.IncludeFilters[].Namespace' | grep -c '^AWS/Redshift$' || true)

    if [ "$RDS_IN" -eq 0 ]; then
      echo "  !! AWS/RDS is NOT in the include list. RDS + Aurora metrics will NOT"
      echo "     reach New Relic until it's added."
    else
      echo "  OK: AWS/RDS is included (covers Aurora too, same namespace)."
    fi

    if [ "$REDSHIFT_IN" -eq 0 ]; then
      echo "  !! AWS/Redshift is NOT in the include list. Redshift metrics will NOT"
      echo "     reach New Relic until it's added."
    else
      echo "  OK: AWS/Redshift is included."
    fi
  fi

  if [ "$HAS_EXCLUDE" = "yes" ]; then
    echo "  This stream uses an EXCLUDE list. Everything flows EXCEPT:"
    echo "$DETAIL" | jq -r '.ExcludeFilters[].Namespace'
    echo "$DETAIL" | jq -r '.ExcludeFilters[].Namespace' | grep -E '^AWS/(RDS|Redshift)$' \
      && echo "  !! One of RDS/Redshift is explicitly excluded -- remove it from ExcludeFilters." \
      || echo "  OK: neither RDS nor Redshift is excluded."
  fi

  echo
done

echo "=================================================================="
echo " Next step: run the NRQL coverage-check pack in New Relic to"
echo " confirm the data is actually landing (not just configured to send)."
echo "=================================================================="

# --- How to fix a missing namespace, for reference ---
#
# aws cloudwatch put-metric-stream \
#   --name "<your-stream-name>" \
#   --firehose-arn "<existing-firehose-arn>" \
#   --role-arn "<existing-role-arn>" \
#   --output-format opentelemetry0.7 \
#   --include-filters Namespace=AWS/RDS Namespace=AWS/Redshift \
#   --region "$REGION"
#
# NOTE: put-metric-stream is a full replace of the filter config, not a merge.
# Pull the existing filter list first (see DETAIL above) and re-supply it in
# full alongside the namespace you're adding, or you'll drop other services.
