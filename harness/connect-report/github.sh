#!/usr/bin/env bash
# Pulls commit + PR context from GitHub for the commit that triggered this deploy.
#
# Requires:
#   GITHUB_TOKEN
#   GITHUB_REPO   - e.g. "my-org/my-service"
#   COMMIT_SHA    - <+codebase.commitSha> in Harness
#   SERVICE_NAME, ENVIRONMENT_NAME
set -euo pipefail

OUT_DIR="${OUT_DIR:-./fetched}"
mkdir -p "$OUT_DIR"

COMMIT=$(curl -sf \
  -H "Authorization: Bearer ${GITHUB_TOKEN}" \
  -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/${GITHUB_REPO}/commits/${COMMIT_SHA}")

PRS=$(curl -sf \
  -H "Authorization: Bearer ${GITHUB_TOKEN}" \
  -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/${GITHUB_REPO}/commits/${COMMIT_SHA}/pulls")

jq -n \
  --arg source "github" \
  --arg service "${SERVICE_NAME:-unknown}" \
  --arg environment "${ENVIRONMENT_NAME:-unknown}" \
  --arg ts "$(date -u +%FT%TZ)" \
  --argjson commit "$COMMIT" \
  --argjson prs "$PRS" \
  '{source_system: $source, service: $service, environment: $environment, timestamp: $ts, payload: {commit: $commit, pull_requests: $prs}}' \
  > "${OUT_DIR}/github.json"

echo "Wrote ${OUT_DIR}/github.json"
