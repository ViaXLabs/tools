#!/usr/bin/env bash
# Pulls a health snapshot for this service from New Relic.
#
# Supports both query paths Harness's own New Relic connector docs mention:
#   nerdgraph - the current, recommended GraphQL API (default)
#   insights  - the older REST "Insights Query API" - New Relic itself has
#               deprecated this in favor of NerdGraph, so treat it as a
#               fallback/compatibility path, not the primary one
#   both      - runs both and stores both results, if you want the
#               redundancy while you're still deciding
#
# These two paths use DIFFERENT credential types - NerdGraph wants a User
# API key (NRAK-...), Insights wants a separate Query Key. They are not
# interchangeable, so this needs two secrets if you use "both" or "insights".
#
# Reuses the same secret (newrelic_api_key) as the newrelic_reporting
# Harness connector for the NerdGraph path - see the comment at the top of
# harness/connectors/newrelic-connector.yaml for why this is a direct API
# call rather than a native step.
#
# Requires:
#   NEW_RELIC_ACCOUNT_ID
#   NEW_RELIC_API_MODE           - "nerdgraph" (default), "insights", or "both"
#   NEW_RELIC_API_KEY            - NerdGraph User API key, same secret as the connector's apiKeyRef
#                                   (required for mode nerdgraph/both)
#   NEW_RELIC_INSIGHTS_QUERY_KEY - Insights Query Key, a different credential - see note above
#                                   (required for mode insights/both)
#   NEW_RELIC_REGION             - "us" (default) or "eu"
#   NEW_RELIC_ENTITY_NAME        - APM app name to filter on, defaults to SERVICE_NAME
#   SERVICE_NAME, ENVIRONMENT_NAME
set -euo pipefail

OUT_DIR="${OUT_DIR:-./fetched}"
mkdir -p "$OUT_DIR"

MODE="${NEW_RELIC_API_MODE:-nerdgraph}"
REGION="${NEW_RELIC_REGION:-us}"
ENTITY="${NEW_RELIC_ENTITY_NAME:-${SERVICE_NAME:-}}"
NRQL="SELECT average(duration), percentage(count(*), WHERE error IS true) AS errorRate, rate(count(*), 1 minute) AS throughput FROM Transaction WHERE appName = '${ENTITY}' SINCE 1 hour ago"

fetch_nerdgraph() {
  local endpoint="https://api.newrelic.com/graphql"
  [[ "$REGION" == "eu" ]] && endpoint="https://api.eu.newrelic.com/graphql"

  local body
  body=$(jq -n \
    --arg nrql "$NRQL" \
    '{
      query: "query($accountId: Int!, $nrql: Nrql!) { actor { account(id: $accountId) { nrql(query: $nrql) { results } } } }",
      variables: { accountId: (env.NEW_RELIC_ACCOUNT_ID | tonumber), nrql: $nrql }
    }')

  curl -sf \
    -H "API-Key: ${NEW_RELIC_API_KEY}" \
    -H "Content-Type: application/json" \
    -d "$body" \
    "$endpoint"
}

fetch_insights() {
  local endpoint="https://insights-api.newrelic.com/v1/accounts/${NEW_RELIC_ACCOUNT_ID}/query"
  [[ "$REGION" == "eu" ]] && endpoint="https://insights-api.eu.newrelic.com/v1/accounts/${NEW_RELIC_ACCOUNT_ID}/query"

  curl -sf -G \
    -H "Accept: application/json" \
    -H "X-Query-Key: ${NEW_RELIC_INSIGHTS_QUERY_KEY}" \
    --data-urlencode "nrql=${NRQL}" \
    "$endpoint"
}

NERDGRAPH_RESULT="null"
INSIGHTS_RESULT="null"

if [[ "$MODE" == "nerdgraph" || "$MODE" == "both" ]]; then
  NERDGRAPH_RESULT=$(fetch_nerdgraph)
fi
if [[ "$MODE" == "insights" || "$MODE" == "both" ]]; then
  INSIGHTS_RESULT=$(fetch_insights)
fi

jq -n \
  --arg source "newrelic" \
  --arg service "${SERVICE_NAME:-unknown}" \
  --arg environment "${ENVIRONMENT_NAME:-unknown}" \
  --arg ts "$(date -u +%FT%TZ)" \
  --arg mode "$MODE" \
  --argjson nerdgraph "$NERDGRAPH_RESULT" \
  --argjson insights "$INSIGHTS_RESULT" \
  '{source_system: $source, service: $service, environment: $environment, timestamp: $ts, payload: {mode: $mode, nerdgraph: $nerdgraph, insights: $insights}}' \
  > "${OUT_DIR}/newrelic.json"

echo "Wrote ${OUT_DIR}/newrelic.json (mode: ${MODE})"
