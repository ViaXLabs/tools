#!/usr/bin/env bash
# Pulls the current pipeline execution's summary from the Harness NG API.
#
# Requires (set as Harness pipeline variables / secrets, backed by Vault):
#   HARNESS_API_KEY      - Harness API key, pulled from Vault as a Harness secret
#   HARNESS_ACCOUNT_ID
#   HARNESS_ORG_ID
#   HARNESS_PROJECT_ID
#   HARNESS_EXECUTION_ID - <+pipeline.executionId> in Harness
#   SERVICE_NAME, ENVIRONMENT_NAME - passed through from pipeline variables
set -euo pipefail

OUT_DIR="${OUT_DIR:-./fetched}"
mkdir -p "$OUT_DIR"

RESP=$(curl -sf \
  -H "x-api-key: ${HARNESS_API_KEY}" \
  "https://app.harness.io/pipeline/api/pipelines/execution/v2/${HARNESS_EXECUTION_ID}?accountIdentifier=${HARNESS_ACCOUNT_ID}&orgIdentifier=${HARNESS_ORG_ID}&projectIdentifier=${HARNESS_PROJECT_ID}")

jq -n \
  --arg source "harness" \
  --arg service "${SERVICE_NAME:-unknown}" \
  --arg environment "${ENVIRONMENT_NAME:-unknown}" \
  --arg ts "$(date -u +%FT%TZ)" \
  --argjson payload "$RESP" \
  '{source_system: $source, service: $service, environment: $environment, timestamp: $ts, payload: $payload}' \
  > "${OUT_DIR}/harness.json"

echo "Wrote ${OUT_DIR}/harness.json"
