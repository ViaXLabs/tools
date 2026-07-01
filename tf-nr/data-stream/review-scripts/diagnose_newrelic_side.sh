#!/usr/bin/env bash
# ============================================================
# diagnose_newrelic_side.sh
# Confirms (via NerdGraph):
#   - AWS account is LINKED in New Relic + per-integration status
#   - metric-stream data is landing in NRDB
#   - which namespaces / stream ARNs arrive, and ingest freshness
#
# Usage:
#   export NR_API_KEY="NRAK-xxxx"   # User API key
#   export NR_ACCOUNT_ID="1234567"
#   export NR_REGION="US"           # US or EU (default US)
#   ./diagnose_newrelic_side.sh
#
# Requires: curl, jq
# ============================================================

set -uo pipefail

: "${NR_API_KEY:?Set NR_API_KEY (User API key, starts with NRAK-)}"
: "${NR_ACCOUNT_ID:?Set NR_ACCOUNT_ID}"
NR_REGION="${NR_REGION:-US}"

if [[ "$NR_REGION" == "EU" ]]; then GQL="https://api.eu.newrelic.com/graphql"
else GQL="https://api.newrelic.com/graphql"; fi

BOLD=$'\033[1m'; DIM=$'\033[2m'; RST=$'\033[0m'
G=$'\033[32m'; R=$'\033[31m'; Y=$'\033[33m'; B=$'\033[36m'
ok()   { printf '   %s\xe2\x9c\x93%s %s\n' "$G" "$RST" "$1"; }
bad()  { printf '   %s\xe2\x9c\x97%s %s\n' "$R" "$RST" "$1"; }
warn() { printf '   %s!%s %s\n' "$Y" "$RST" "$1"; }
info() { printf '     %s%s%s\n' "$DIM" "$1" "$RST"; }
kv()   { printf '     %-26s %s\n' "$1" "$2"; }
section(){ printf '\n%s== %s ==%s\n' "$B$BOLD" "$1" "$RST"; }

# POST a GraphQL document built safely with jq (handles quoting/escaping).
gql() {  # $1 = graphql document string
  local doc="$1" payload
  payload="$(jq -n --arg q "$doc" '{query:$q}')"
  curl -s -X POST "$GQL" \
    -H "Content-Type: application/json" \
    -H "API-Key: ${NR_API_KEY}" \
    --data "$payload"
}

# Run an NRQL query through NerdGraph; echoes the .results JSON array.
nrql() {  # $1 = NRQL string
  local q="$1"
  gql "{ actor { account(id: ${NR_ACCOUNT_ID}) { nrql(query: \"${q//\"/\\\"}\") { results } } } }"
}

V_LINKED=0; V_DATA=0

printf '\n%s%s  New Relic Setup & Data Checker%s\n' "$BOLD" "$B" "$RST"
kv "Account"  "$NR_ACCOUNT_ID"
kv "Region"   "$NR_REGION"
kv "Endpoint" "$GQL"

# ---- 0. key sanity ----------------------------------------
section "0 - API key / access"
WHO="$(gql '{ actor { user { name email } } }')"
if echo "$WHO" | jq -e '.errors' >/dev/null 2>&1; then
  bad "NerdGraph error:"; echo "$WHO" | jq -r '.errors[].message' | sed 's/^/       /'
  info "Ensure NR_API_KEY is a USER key (NRAK-) and NR_REGION matches the account."
  exit 1
fi
kv "User"  "$(echo "$WHO" | jq -r '.data.actor.user.name')"
kv "Email" "$(echo "$WHO" | jq -r '.data.actor.user.email')"
ok "Authenticated."

# ---- 1. linked accounts + per-integration status ----------
section "1 - Linked AWS accounts (link_account step)"
LINKED="$(gql "{ actor { account(id: ${NR_ACCOUNT_ID}) { cloud { linkedAccounts { id name createdAt integrations { name } } } } } }")"
if echo "$LINKED" | jq -e '.errors' >/dev/null 2>&1; then
  bad "NerdGraph error:"; echo "$LINKED" | jq -r '.errors[].message' | sed 's/^/       /'
else
  COUNT="$(echo "$LINKED" | jq '[.data.actor.account.cloud.linkedAccounts[]?] | length')"
  if [[ "${COUNT:-0}" -eq 0 ]]; then
    bad "No linked AWS accounts. The link_account resource never registered."
    info "Nothing will flow until it does - re-apply and verify the role ARN + external id."
  else
    V_LINKED=1
    ok "Found ${COUNT} linked account(s):"
    echo "$LINKED" | jq -r '.data.actor.account.cloud.linkedAccounts[]
      | "       [\(.id)] \(.name)  (created \(.createdAt))\n         integrations: \([.integrations[].name] | join(", ") // "none")"'
  fi
fi

# ---- 2. is metric-stream data landing? --------------------
section "2 - Metric-stream data in NRDB (last 30 min)"
R="$(nrql "FROM Metric SELECT count(*) WHERE collector.name = 'cloudwatch-metric-streams' SINCE 30 minutes ago")"
if echo "$R" | jq -e '.errors' >/dev/null 2>&1; then
  bad "Query error:"; echo "$R" | jq -r '.errors[].message' | sed 's/^/       /'
else
  CNT="$(echo "$R" | jq -r '.data.actor.account.nrql.results[0].count // 0')"
  kv "Data points" "$CNT"
  if [[ "${CNT:-0}" -gt 0 ]]; then ok "Data IS arriving from a metric stream."; V_DATA=1
  else bad "ZERO metric-stream data points in NRDB."; fi
fi

# ---- 3. namespaces ----------------------------------------
section "3 - Namespaces arriving (last 1h)"
R="$(nrql "FROM Metric SELECT uniques(aws.Namespace) WHERE collector.name = 'cloudwatch-metric-streams' SINCE 1 hour ago")"
NS_LIST="$(echo "$R" | jq -r '.data.actor.account.nrql.results[0]["uniques.aws.Namespace"][]? // empty')"
if [[ -n "$NS_LIST" ]]; then
  echo "$NS_LIST" | sed 's/^/       - /'
  ok "$(echo "$NS_LIST" | wc -l | tr -d ' ') namespace(s) flowing."
else
  warn "No namespaces - check include/exclude filters on the metric stream."
fi

# ---- 4. stream ARNs (confirm it's yours) ------------------
section "4 - Source stream ARNs (last 1h)"
R="$(nrql "FROM Metric SELECT count(*) WHERE collector.name = 'cloudwatch-metric-streams' FACET aws.MetricStreamArn SINCE 1 hour ago")"
ARNS="$(echo "$R" | jq -r '.data.actor.account.nrql.results[]? | "       \(.["aws.MetricStreamArn"] // "unknown"): \(.count)"')"
[[ -n "$ARNS" ]] && echo "$ARNS" || warn "No stream ARNs found."

# ---- 5. freshness timeseries ------------------------------
section "5 - Ingest trend (per 5 min, last 30 min)"
R="$(nrql "FROM Metric SELECT count(*) WHERE collector.name = 'cloudwatch-metric-streams' TIMESERIES 5 minutes SINCE 30 minutes ago")"
echo "$R" | jq -r '.data.actor.account.nrql.results[]?
  | "       \(.beginTimeSeconds | todate)  \(.count)"' 2>/dev/null | tail -6 \
  || warn "No timeseries data."

# ---- verdict ----------------------------------------------
section "VERDICT"
if   [[ "$V_LINKED" -eq 0 ]]; then
  bad "AWS account is NOT linked in New Relic - fix the link_account resource first."
elif [[ "$V_DATA" -eq 1 ]]; then
  ok  "Linked AND receiving data. New Relic side is healthy."
else
  bad "Account linked but NO data arriving. Cross-check with the AWS script:"
  info "AWS DeliveryToHttpEndpoint.Success > 0 but NR = 0  -> wrong account/key/region on Firehose."
  info "S3 backup bucket has objects                       -> NR rejected the data (read those objects)."
fi
printf '\n'
