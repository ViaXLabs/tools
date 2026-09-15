#!/usr/bin/env bash
# Pulls artifact metadata (checksum, size, storage path) from the plain
# Nexus Repository for the artifact this deploy is using. No Nexus IQ /
# scan / policy data here on purpose.
#
# Reuses the same secret (nexus_password) as the nexus_reporting Harness
# connector (see harness/connectors/nexus-connector.yaml).
#
# Requires:
#   NEXUS_SERVER_URL   - e.g. https://nexus.yourcompany.com
#   NEXUS_USERNAME      - same as the connector's username
#   NEXUS_PASSWORD      - same secret as the connector's passwordRef
#   NEXUS_REPOSITORY    - repository name, e.g. maven-releases
#   NEXUS_COMPONENT     - component/artifact name
#   NEXUS_VERSION       - artifact version (defaults to SERVICE_VERSION)
#   SERVICE_NAME, ENVIRONMENT_NAME
set -euo pipefail

OUT_DIR="${OUT_DIR:-./fetched}"
mkdir -p "$OUT_DIR"

VERSION="${NEXUS_VERSION:-${SERVICE_VERSION:-}}"

PAYLOAD=$(curl -sf -u "${NEXUS_USERNAME}:${NEXUS_PASSWORD}" \
  -G \
  --data-urlencode "repository=${NEXUS_REPOSITORY}" \
  --data-urlencode "name=${NEXUS_COMPONENT}" \
  --data-urlencode "version=${VERSION}" \
  "${NEXUS_SERVER_URL}/service/rest/v1/search")

jq -n \
  --arg source "nexus" \
  --arg service "${SERVICE_NAME:-unknown}" \
  --arg environment "${ENVIRONMENT_NAME:-unknown}" \
  --arg ts "$(date -u +%FT%TZ)" \
  --argjson payload "$PAYLOAD" \
  '{source_system: $source, service: $service, environment: $environment, timestamp: $ts, payload: $payload}' \
  > "${OUT_DIR}/nexus.json"

echo "Wrote ${OUT_DIR}/nexus.json"
