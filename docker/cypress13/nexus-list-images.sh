#!/usr/bin/env bash
# nexus-list-images.sh
#
# Lists every image:tag hosted in a Nexus Docker (hosted/proxy/group)
# repository, using the standard Docker Registry HTTP API v2 that Nexus
# implements for docker-format repos — so this works the same way it
# would against Harbor, ECR, GHCR, or any other v2-compliant registry.
#
# Requires: curl, jq
#
# Env vars (required):
#   NEXUS_REGISTRY   host[:port] of the registry endpoint, e.g. nexus.mycorp.com:8083
#                     (this is the docker-connector port, not the Nexus web UI port)
#   NEXUS_USER        registry username
#   NEXUS_PASS        registry password or token
#     -> Set these as CI secrets. Never hardcode them into this file.
#
# Env vars (optional):
#   OUT_FILE          output file, default nexus-images.txt
#   PAGE_SIZE         catalog page size, default 100
#
# Output: OUT_FILE with one "repo:tag" per line, e.g.
#   team/app-a:1.0.0
#   team/app-a:latest
#   infra/base-alpine:3.20

set -eu

: "${NEXUS_REGISTRY:?Set NEXUS_REGISTRY, e.g. nexus.mycorp.com:8083}"
: "${NEXUS_USER:?Set NEXUS_USER}"
: "${NEXUS_PASS:?Set NEXUS_PASS}"

OUT_FILE="${OUT_FILE:-nexus-images.txt}"
PAGE_SIZE="${PAGE_SIZE:-100}"

: > "$OUT_FILE"
REPOS_TMP=$(mktemp)
trap 'rm -f "$REPOS_TMP"' EXIT

echo "Fetching repository catalog from $NEXUS_REGISTRY ..."

NEXT="/v2/_catalog?n=$PAGE_SIZE"
PAGES=0
while [ -n "$NEXT" ]; do
  PAGES=$((PAGES + 1))
  HEADERS_TMP=$(mktemp)
  BODY=$(curl -sS -f -D "$HEADERS_TMP" -u "$NEXUS_USER:$NEXUS_PASS" "https://$NEXUS_REGISTRY$NEXT") || {
    echo "Catalog request failed for $NEXT" >&2
    cat "$HEADERS_TMP" >&2
    rm -f "$HEADERS_TMP"
    exit 2
  }
  echo "$BODY" | jq -r '.repositories[]?' >> "$REPOS_TMP"

  # Docker Registry v2 pagination: Link: </v2/_catalog?last=X&n=Y>; rel="next"
  LINK=$(grep -i '^Link:' "$HEADERS_TMP" | sed -E 's/^[Ll]ink: *<([^>]+)>.*/\1/' | tr -d '\r')
  rm -f "$HEADERS_TMP"
  NEXT="$LINK"

  if [ "$PAGES" -gt 500 ]; then
    echo "Stopping after 500 pages — check PAGE_SIZE or registry pagination." >&2
    break
  fi
done

TOTAL_REPOS=$(wc -l < "$REPOS_TMP" | tr -d ' ')
echo "Found $TOTAL_REPOS repositories. Fetching tags for each ..."

COUNT=0
while IFS= read -r REPO; do
  [ -z "$REPO" ] && continue
  TAGS_JSON=$(curl -sS -f -u "$NEXUS_USER:$NEXUS_PASS" "https://$NEXUS_REGISTRY/v2/$REPO/tags/list") || {
    echo "  WARN: tag list failed for $REPO, skipping" >&2
    continue
  }
  echo "$TAGS_JSON" | jq -r --arg repo "$REPO" '.tags[]? | "\($repo):\(.)"' >> "$OUT_FILE"
  COUNT=$((COUNT + 1))
done < "$REPOS_TMP"

TOTAL_IMAGES=$(wc -l < "$OUT_FILE" | tr -d ' ')
echo "Wrote $TOTAL_IMAGES image:tag entries across $COUNT repositories to $OUT_FILE"
