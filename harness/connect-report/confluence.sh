#!/usr/bin/env bash
# Pulls doc/runbook page metadata from Confluence for this service, so the
# report can show whether docs look stale (last-updated timestamp + link).
#
# Reuses the same secret (confluence_api_token) registered on the
# confluence_reporting Harness connector (see
# harness/connectors/confluence-connector.yaml) - same reasoning as jira.sh.
#
# Requires:
#   CONFLUENCE_BASE_URL   - e.g. https://yourcompany.atlassian.net/wiki
#   CONFLUENCE_EMAIL      - same value as the connector's `username`
#   CONFLUENCE_API_TOKEN  - same secret as the connector's `passwordRef`
#   CONFLUENCE_SPACE_KEY
#   SERVICE_NAME, ENVIRONMENT_NAME
set -euo pipefail

OUT_DIR="${OUT_DIR:-./fetched}"
mkdir -p "$OUT_DIR"

AUTH=$(printf '%s:%s' "${CONFLUENCE_EMAIL}" "${CONFLUENCE_API_TOKEN}" | base64)

RESULTS=$(curl -sf -G \
  -H "Authorization: Basic ${AUTH}" \
  --data-urlencode "cql=space=\"${CONFLUENCE_SPACE_KEY}\" AND title~\"${SERVICE_NAME}\"" \
  --data-urlencode "expand=version" \
  "${CONFLUENCE_BASE_URL}/rest/api/content/search")

jq -n \
  --arg source "confluence" \
  --arg service "${SERVICE_NAME:-unknown}" \
  --arg environment "${ENVIRONMENT_NAME:-unknown}" \
  --arg ts "$(date -u +%FT%TZ)" \
  --argjson payload "$RESULTS" \
  '{source_system: $source, service: $service, environment: $environment, timestamp: $ts, payload: $payload}' \
  > "${OUT_DIR}/confluence.json"

echo "Wrote ${OUT_DIR}/confluence.json"
