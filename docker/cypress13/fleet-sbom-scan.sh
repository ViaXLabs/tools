#!/usr/bin/env bash
# fleet-sbom-scan.sh
#
# Takes the image list from nexus-list-images.sh, generates a real SBOM
# (CycloneDX JSON, via Syft) for every image directly against the
# registry — no docker pull / no local daemon needed — then rolls a
# curated subset of package versions (the "stuff we care about") into
# one consolidated CSV so you don't have to open 200 SBOM files by hand.
#
# Requires: docker (just for `docker login`, to hand Syft working
#           registry credentials via the standard Docker config), syft, jq
#           Install syft: https://github.com/anchore/syft#installation
#
# Usage:
#   ./fleet-sbom-scan.sh <images-file>
#
# Env vars (required):
#   NEXUS_REGISTRY   host[:port] of the registry endpoint
#   NEXUS_USER       registry username
#   NEXUS_PASS       registry password or token
#
# Env vars (optional):
#   INTERESTED_PACKAGES   space-separated package names to pull out into
#                         their own CSV columns. Default below covers
#                         what came up earlier in this conversation —
#                         edit freely, e.g. add "alpine-baselayout git".
#   SBOM_DIR              where full per-image SBOMs are archived, default "sboms"
#   SUMMARY_CSV            consolidated report path, default "fleet-versions.csv"
#
# Output:
#   SUMMARY_CSV  — one row per image:tag, one column per interested package
#   SBOM_DIR/    — full CycloneDX SBOM per image, for anything not in
#                  the curated list, or for a deeper compliance/audit pass

set -eu

IMAGE_LIST="${1:?Usage: $0 <images-file>}"
: "${NEXUS_REGISTRY:?Set NEXUS_REGISTRY}"
: "${NEXUS_USER:?Set NEXUS_USER}"
: "${NEXUS_PASS:?Set NEXUS_PASS}"

INTERESTED_PACKAGES="${INTERESTED_PACKAGES:-node npm cypress python python3}"
SBOM_DIR="${SBOM_DIR:-sboms}"
SUMMARY_CSV="${SUMMARY_CSV:-fleet-versions.csv}"

mkdir -p "$SBOM_DIR"

echo "Logging in to $NEXUS_REGISTRY (so syft can reuse the Docker credential store) ..."
echo "$NEXUS_PASS" | docker login "$NEXUS_REGISTRY" -u "$NEXUS_USER" --password-stdin

# Build the CSV header once, from whatever package list you configured.
HEADER="repository,tag"
for PKG in $INTERESTED_PACKAGES; do
  HEADER="$HEADER,${PKG}_version"
done
HEADER="$HEADER,sbom_path"
echo "$HEADER" > "$SUMMARY_CSV"

TOTAL=0
FAILED=0

while IFS= read -r LINE; do
  [ -z "$LINE" ] && continue
  TOTAL=$((TOTAL + 1))
  REPO="${LINE%%:*}"
  TAG="${LINE##*:}"
  SAFE_NAME=$(echo "$REPO" | tr '/:' '__')
  SBOM_FILE="$SBOM_DIR/${SAFE_NAME}_${TAG}.cdx.json"

  echo "[$TOTAL] Scanning $REPO:$TAG ..."
  ERR_TMP=$(mktemp)
  if ! syft scan "registry:$NEXUS_REGISTRY/$REPO:$TAG" -o "cyclonedx-json=$SBOM_FILE" >"$ERR_TMP" 2>&1; then
    echo "  FAILED — see below:" >&2
    cat "$ERR_TMP" >&2
    FAILED=$((FAILED + 1))
    ROW="$REPO,$TAG"
    for _ in $INTERESTED_PACKAGES; do ROW="$ROW,scan-failed"; done
    ROW="$ROW,"
    echo "$ROW" >> "$SUMMARY_CSV"
    rm -f "$ERR_TMP"
    continue
  fi
  rm -f "$ERR_TMP"

  ROW="$REPO,$TAG"
  for PKG in $INTERESTED_PACKAGES; do
    VER=$(jq -r --arg n "$PKG" '[.components[]? | select(.name==$n)][0].version // "not found"' "$SBOM_FILE")
    ROW="$ROW,$VER"
  done
  ROW="$ROW,$SBOM_FILE"
  echo "$ROW" >> "$SUMMARY_CSV"
done < "$IMAGE_LIST"

echo ""
echo "Done: $TOTAL images scanned, $FAILED failed."
echo "Summary:   $SUMMARY_CSV"
echo "Full SBOMs: $SBOM_DIR/"
