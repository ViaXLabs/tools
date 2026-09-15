#!/usr/bin/env bash
# Pulls Jira issues linked to this deploy.
#
# Harness's native Jira steps only support Create/Update/Approval, not
# search/read - so this hits the Jira REST API directly, but reuses the
# exact same secret (jira_api_token) registered on the jira_reporting
# Harness connector (see harness/connectors/jira-connector.yaml), so there's
# one tested credential instead of a second ad-hoc one.
#
# Two ways to select issues - pick whichever fits your commit convention:
#   1) You already know the issue key(s), e.g. parsed from the commit
#      message - set JIRA_ISSUE_KEYS (comma-separated)
#   2) You want to search by JQL instead - set JIRA_JQL
#
# Requires:
#   JIRA_BASE_URL   - e.g. https://yourcompany.atlassian.net
#   JIRA_EMAIL      - same value as the connector's `username`
#   JIRA_API_TOKEN  - same secret as the connector's `passwordRef` (jira_api_token)
#   SERVICE_NAME, ENVIRONMENT_NAME
set -euo pipefail

OUT_DIR="${OUT_DIR:-./fetched}"
mkdir -p "$OUT_DIR"

AUTH=$(printf '%s:%s' "${JIRA_EMAIL}" "${JIRA_API_TOKEN}" | base64)

if [[ -n "${JIRA_ISSUE_KEYS:-}" ]]; then
  IFS=',' read -ra KEYS <<< "${JIRA_ISSUE_KEYS}"
  ISSUES="[]"
  for KEY in "${KEYS[@]}"; do
    ISSUE=$(curl -sf -H "Authorization: Basic ${AUTH}" \
      "${JIRA_BASE_URL}/rest/api/3/issue/${KEY}")
    ISSUES=$(jq -n --argjson arr "$ISSUES" --argjson i "$ISSUE" '$arr + [$i]')
  done
else
  JQL="${JIRA_JQL:-project=OPS AND fixVersion=\"${SERVICE_VERSION:-}\"}"
  ISSUES=$(curl -sf -G -H "Authorization: Basic ${AUTH}" \
    --data-urlencode "jql=${JQL}" \
    "${JIRA_BASE_URL}/rest/api/3/search" | jq '.issues')
fi

jq -n \
  --arg source "jira" \
  --arg service "${SERVICE_NAME:-unknown}" \
  --arg environment "${ENVIRONMENT_NAME:-unknown}" \
  --arg ts "$(date -u +%FT%TZ)" \
  --argjson issues "$ISSUES" \
  '{source_system: $source, service: $service, environment: $environment, timestamp: $ts, payload: {issues: $issues}}' \
  > "${OUT_DIR}/jira.json"

echo "Wrote ${OUT_DIR}/jira.json"
