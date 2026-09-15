#!/usr/bin/env bash
# Pulls sync/health status from ArgoCD for the deployed application.
#
# Requires:
#   ARGOCD_SERVER   - e.g. argocd.internal.company.com
#   ARGOCD_TOKEN
#   ARGOCD_APP_NAME
#   SERVICE_NAME, ENVIRONMENT_NAME
set -euo pipefail

OUT_DIR="${OUT_DIR:-./fetched}"
mkdir -p "$OUT_DIR"

PAYLOAD=$(curl -sf \
  -H "Authorization: Bearer ${ARGOCD_TOKEN}" \
  "https://${ARGOCD_SERVER}/api/v1/applications/${ARGOCD_APP_NAME}")

jq -n \
  --arg source "argocd" \
  --arg service "${SERVICE_NAME:-unknown}" \
  --arg environment "${ENVIRONMENT_NAME:-unknown}" \
  --arg ts "$(date -u +%FT%TZ)" \
  --argjson payload "$PAYLOAD" \
  '{source_system: $source, service: $service, environment: $environment, timestamp: $ts, payload: $payload}' \
  > "${OUT_DIR}/argocd.json"

echo "Wrote ${OUT_DIR}/argocd.json"
