#!/usr/bin/env bash
# ============================================================
# diagnose_aws_side.sh
# Walks the data path:  CloudWatch -> Metric Stream -> Firehose
#                       -> NR endpoint  (+ S3 backup, + error logs)
# and prints a per-hop report with a final verdict.
#
# Portable: works on both GNU (Linux) and BSD (macOS) date/tools.
#
# Usage:
#   ./diagnose_aws_side.sh <NAME> [REGION]
#     <NAME>   = the var.name suffix used in Terraform (e.g. "prod")
#     [REGION] = AWS region (default: us-east-1)
#
# Requires: awscli v2, jq
# ============================================================

set -uo pipefail

NAME="${1:?Usage: ./diagnose_aws_side.sh <NAME> [REGION]}"
REGION="${2:-us-east-1}"

STREAM_NAME="newrelic-metric-stream-${NAME}"
FIREHOSE_NAME="newrelic_firehose_stream_${NAME}"

# ---- portable "1 hour ago" (GNU vs BSD) -------------------
if date -u -d '1 hour ago' +%s >/dev/null 2>&1; then
  START="$(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%SZ)"   # GNU
else
  START="$(date -u -v-1H +%Y-%m-%dT%H:%M:%SZ)"             # BSD
fi
END="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# ---- presentation helpers ---------------------------------
BOLD=$'\033[1m'; DIM=$'\033[2m'; RST=$'\033[0m'
G=$'\033[32m'; R=$'\033[31m'; Y=$'\033[33m'; B=$'\033[36m'
ok()   { printf '   %s\xe2\x9c\x93%s %s\n' "$G" "$RST" "$1"; }
bad()  { printf '   %s\xe2\x9c\x97%s %s\n' "$R" "$RST" "$1"; }
warn() { printf '   %s!%s %s\n' "$Y" "$RST" "$1"; }
info() { printf '     %s%s%s\n' "$DIM" "$1" "$RST"; }
kv()   { printf '     %-26s %s\n' "$1" "$2"; }
section() {
  printf '\n%s== %s ==%s\n' "$B$BOLD" "$1" "$RST"
}

# sum/avg a CloudWatch metric over the window
stat() {  # $1 ns  $2 metric  $3 dimName  $4 dimVal  $5 stat(Sum|Average)
  aws cloudwatch get-metric-statistics --region "$REGION" \
    --namespace "$1" --metric-name "$2" \
    --dimensions "Name=$3,Value=$4" \
    --start-time "$START" --end-time "$END" \
    --period 300 --statistics "$5" \
    --query "Datapoints[].$5" --output text 2>/dev/null \
  | tr '\t' '\n' | awk '{s+=$1} END {printf "%.4f", s+0}'
}
gt0() { awk "BEGIN{exit !(${1:-0} > 0)}"; }

# state captured for the verdict
V_EMIT=0; V_REC_IN=0; V_DEL_OK=0; V_REJECTED=0

printf '\n%s%s  AWS -> New Relic Metric Stream Diagnostic%s\n' "$BOLD" "$B" "$RST"
kv "Name suffix" "$NAME"
kv "Region"      "$REGION"
kv "Window"      "$START -> $END"

# ---- 0. identity ------------------------------------------
section "0 - AWS credentials"
ID_JSON="$(aws sts get-caller-identity --region "$REGION" 2>/dev/null)"
if [[ -z "$ID_JSON" ]]; then
  bad "Cannot authenticate to AWS. Run 'aws configure' / SSO login first."; exit 1
fi
kv "Account" "$(echo "$ID_JSON" | jq -r '.Account')"
kv "ARN"     "$(echo "$ID_JSON" | jq -r '.Arn')"
ok "Authenticated."

# ---- 1. metric stream state -------------------------------
section "1 - Metric Stream state"
MS="$(aws cloudwatch get-metric-stream --region "$REGION" --name "$STREAM_NAME" 2>/dev/null)"
if [[ -z "$MS" ]]; then
  bad "Stream '$STREAM_NAME' not found (wrong NAME suffix, or never created)."
else
  STATE="$(echo "$MS" | jq -r '.State')"
  OUTFMT="$(echo "$MS" | jq -r '.OutputFormat')"
  kv "State"        "$STATE"
  kv "OutputFormat" "$OUTFMT"
  kv "Firehose ARN" "$(echo "$MS" | jq -r '.FirehoseArn')"
  kv "Role ARN"     "$(echo "$MS" | jq -r '.RoleArn')"
  if [[ "$STATE" == "running" ]]; then ok "Stream is running."
  else bad "Stream is NOT running (state=$STATE). Re-apply / start it."; fi
  [[ "$OUTFMT" == "opentelemetry0.7" ]] && warn "opentelemetry1.0 is the current recommended format."
fi

# ---- 2. is it emitting? -----------------------------------
section "2 - Metric Stream throughput"
UP="$(stat AWS/CloudWatch/MetricStreams MetricUpdate MetricStreamName "$STREAM_NAME" Sum)"
ER="$(stat AWS/CloudWatch/MetricStreams PublishErrorRate MetricStreamName "$STREAM_NAME" Average)"
kv "MetricUpdate (sum, 1h)"     "${UP:-0}"
kv "PublishErrorRate (avg, 1h)" "${ER:-0}"
if gt0 "$UP"; then ok "Stream is emitting metrics."; V_EMIT=1
else bad "No metric updates - check include/exclude filters or that source metrics exist."; fi
gt0 "$ER" && bad "Publish errors present - metric-stream IAM role may lack firehose:PutRecord."

# ---- 3. firehose status + delivery ------------------------
section "3 - Firehose status & delivery"
FH="$(aws firehose describe-delivery-stream --region "$REGION" --delivery-stream-name "$FIREHOSE_NAME" 2>/dev/null)"
BUCKET_NAME=""; LOG_GROUP=""; LOG_ENABLED="false"
if [[ -z "$FH" ]]; then
  bad "Firehose '$FIREHOSE_NAME' not found."
else
  D='.DeliveryStreamDescription.Destinations[0].HttpEndpointDestinationDescription'
  FH_STATUS="$(echo "$FH" | jq -r '.DeliveryStreamDescription.DeliveryStreamStatus')"
  FH_URL="$(echo "$FH" | jq -r "$D.EndpointConfiguration.Url // \"n/a\"")"
  FH_BUCKET_ARN="$(echo "$FH" | jq -r "$D.S3DestinationDescription.BucketARN // \"n/a\"")"
  LOG_ENABLED="$(echo "$FH" | jq -r "$D.CloudWatchLoggingOptions.Enabled // false")"
  LOG_GROUP="$(echo "$FH" | jq -r "$D.CloudWatchLoggingOptions.LogGroupName // \"\"")"
  kv "Status"      "$FH_STATUS"
  kv "NR endpoint" "$FH_URL"
  kv "S3 backup"   "$FH_BUCKET_ARN"
  [[ "$FH_BUCKET_ARN" != "n/a" ]] && BUCKET_NAME="${FH_BUCKET_ARN##*:::}"
  if [[ "$FH_STATUS" == "ACTIVE" ]]; then ok "Firehose ACTIVE."
  else bad "Firehose not ACTIVE (status=$FH_STATUS)."; fi
  case "$FH_URL" in
    *eu01*)                 warn "EU endpoint - confirm NR account is EU and provider region=EU." ;;
    *aws-api.newrelic.com*) info "US endpoint - confirm NR account is US." ;;
  esac

  REC_IN="$(stat AWS/Firehose IncomingRecords DeliveryStreamName "$FIREHOSE_NAME" Sum)"
  DEL_OK="$(stat AWS/Firehose DeliveryToHttpEndpoint.Success DeliveryStreamName "$FIREHOSE_NAME" Sum)"
  printf '\n'
  kv "IncomingRecords (1h)"            "${REC_IN:-0}"
  kv "DeliveryToHttpEndpoint.Success"  "${DEL_OK:-0}"
  gt0 "$REC_IN" && { ok "Firehose is receiving records from the stream."; V_REC_IN=1; } \
                || bad "Firehose receiving nothing - break is stream->firehose (IAM role)."
  gt0 "$DEL_OK" && { ok "Firehose is delivering to New Relic."; V_DEL_OK=1; } \
                || bad "No successful HTTP delivery - check endpoint URL + license key."
fi

# ---- 4. error logging (gap fix #1) ------------------------
section "4 - Firehose error logging"
if [[ "$LOG_ENABLED" == "true" && -n "$LOG_GROUP" ]]; then
  ok "CloudWatch logging enabled: $LOG_GROUP"
  info "Read recent delivery errors with:"
  info "  aws logs tail \"$LOG_GROUP\" --region $REGION --since 1h --format short"
else
  warn "CloudWatch error logging is DISABLED on this Firehose."
  info "Without it, New Relic's HTTP rejection reason is only in the S3 backup objects (section 5)."
  info "To enable: set cloudwatch_logging_options in the Firehose http_endpoint_configuration."
fi

# ---- 5. S3 backup - point to rejected records -------------
section "5 - S3 backup bucket (rejected records)"
if [[ -n "$BUCKET_NAME" ]]; then
  kv "Bucket" "s3://${BUCKET_NAME}/"
  OBJ_COUNT="$(aws s3 ls "s3://${BUCKET_NAME}/" --region "$REGION" --recursive 2>/dev/null | wc -l | tr -d ' ')"
  kv "Object count" "${OBJ_COUNT:-0}"
  if [[ "${OBJ_COUNT:-0}" -gt 0 ]]; then
    V_REJECTED=1
    bad "Rejected records present - data reaches NR but is being REFUSED."
    info "Newest rejected objects:"
    aws s3 ls "s3://${BUCKET_NAME}/" --region "$REGION" --recursive 2>/dev/null | sort | tail -3 \
      | awk '{print "       "$0}'
    info "Inspect one (decode NR's response yourself):"
    info "  aws s3 cp s3://${BUCKET_NAME}/<key> - | gunzip | jq ."
  else
    ok "No rejected records in backup."
  fi
else
  warn "Could not resolve backup bucket from Firehose config."
fi

# ---- 6. AWS Config (gap fix #3) ---------------------------
section "6 - AWS Config (entity metadata enrichment)"
CFG="$(aws configservice describe-configuration-recorder-status --region "$REGION" 2>/dev/null)"
if [[ -z "$CFG" ]]; then
  warn "AWS Config not enabled in $REGION (or no permission to read it)."
  info "New Relic uses Config to enrich metrics with resource metadata/entities."
  info "Metrics still flow without it, but entities may be sparsely decorated."
else
  REC_ON="$(echo "$CFG" | jq -r '.ConfigurationRecordersStatus[0].recording // false')"
  [[ "$REC_ON" == "true" ]] && ok "AWS Config is recording." \
                            || warn "AWS Config recorder exists but is NOT recording."
fi

# ---- verdict ----------------------------------------------
section "VERDICT"
if   [[ "$V_REJECTED" -eq 1 ]]; then
  bad "Data reaches New Relic but is REJECTED."
  info "Fix: license key (40 hex chars) OR US/EU region mismatch OR wrong NR account."
  info "Read a backup object (section 5) for the exact reason."
elif [[ "$V_DEL_OK" -eq 1 ]]; then
  ok  "AWS side is delivering successfully."
  info "If New Relic shows no data, the problem is the NR link - run diagnose_newrelic_side.sh."
elif [[ "$V_REC_IN" -eq 1 ]]; then
  bad "Firehose has records but no successful delivery."
  info "Check the NR endpoint URL and the access_key (license key) on the Firehose."
elif [[ "$V_EMIT" -eq 1 ]]; then
  bad "Stream emits, but Firehose isn't receiving."
  info "Check the metric-stream IAM role grants firehose:PutRecord to this stream."
else
  bad "Nothing flowing from the Metric Stream."
  info "Check stream state, include/exclude filters, and the metric-stream IAM role."
fi
printf '\n'
