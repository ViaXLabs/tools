#!/usr/bin/env bash
# Pulls cluster/service state from AWS ECS or EKS.
#
# Requires:
#   AWS_REGION
#   CLUSTER_TYPE       - "ecs" or "eks"
#   CLUSTER_NAME
#   ECS_SERVICE_NAME               - required when CLUSTER_TYPE=ecs
#   EKS_NAMESPACE, EKS_DEPLOYMENT_NAME - required when CLUSTER_TYPE=eks
#   SERVICE_NAME, ENVIRONMENT_NAME
#
# Auth: assumes an IAM role already available to the pipeline runner
# (a read-only policy is enough for reporting - don't reuse deploy credentials here)
set -euo pipefail

OUT_DIR="${OUT_DIR:-./fetched}"
mkdir -p "$OUT_DIR"

if [[ "${CLUSTER_TYPE}" == "ecs" ]]; then
  PAYLOAD=$(aws ecs describe-services \
    --region "${AWS_REGION}" \
    --cluster "${CLUSTER_NAME}" \
    --services "${ECS_SERVICE_NAME}")
elif [[ "${CLUSTER_TYPE}" == "eks" ]]; then
  PAYLOAD=$(kubectl --context "${CLUSTER_NAME}" -n "${EKS_NAMESPACE}" \
    get deployment "${EKS_DEPLOYMENT_NAME}" -o json)
else
  echo "CLUSTER_TYPE must be ecs or eks" >&2
  exit 1
fi

jq -n \
  --arg source "aws" \
  --arg cluster_type "${CLUSTER_TYPE}" \
  --arg service "${SERVICE_NAME:-unknown}" \
  --arg environment "${ENVIRONMENT_NAME:-unknown}" \
  --arg ts "$(date -u +%FT%TZ)" \
  --argjson payload "$PAYLOAD" \
  '{source_system: $source, cluster_type: $cluster_type, service: $service, environment: $environment, timestamp: $ts, payload: $payload}' \
  > "${OUT_DIR}/aws.json"

echo "Wrote ${OUT_DIR}/aws.json"
