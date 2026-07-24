#!/usr/bin/env bash
# image-version-audit.sh
#
# Opens a built Docker image and reports what's ACTUALLY installed inside it
# (OS, Node, npm, Python, Cypress), instead of trusting whatever version
# label your pipeline matrix attached at build time.
#
# Usage:
#   ./image-version-audit.sh <image:tag> [expected_cypress_version] [expected_node_version]
#
# Examples:
#   ./image-version-audit.sh myorg/ci-runner:node22-cypress13
#   ./image-version-audit.sh myorg/ci-runner:node22-cypress13 13 22
#
# Exit codes:
#   0 = report written, no expected-version mismatch
#   1 = report written, but actual versions did NOT match what was expected
#   2 = couldn't run/inspect the image at all
#
# Output files (override paths via OUT_JSON / OUT_MD env vars):
#   version-report.json
#   version-report.md
#
# To add another tool to check, add one more "===NAME===" block to
# INNER_SCRIPT below, then one more get_section call further down.

set -eu

IMAGE="${1:?Usage: $0 <image:tag> [expected_cypress_version] [expected_node_version]}"
EXPECTED_CYPRESS="${2:-}"
EXPECTED_NODE="${3:-}"
OUT_JSON="${OUT_JSON:-version-report.json}"
OUT_MD="${OUT_MD:-version-report.md}"

echo "Inspecting $IMAGE ..."

# Everything below runs INSIDE the container via `sh`, so it has to stay
# POSIX/busybox-safe (Alpine's default shell is ash, not bash) — no
# bashisms here even though the outer script is bash.
INNER_SCRIPT='
  echo "===OS==="
  (cat /etc/os-release 2>/dev/null | grep -E "^(PRETTY_NAME|VERSION_ID)=") || echo "PRETTY_NAME=unknown"

  echo "===NODE==="
  node --version 2>/dev/null || echo "not installed"

  echo "===NPM==="
  npm --version 2>/dev/null || echo "not installed"

  echo "===PYTHON==="
  (python3 --version 2>/dev/null) || (python --version 2>/dev/null) || echo "not installed"

  echo "===CYPRESS==="
  (npx --no-install cypress version 2>/dev/null) || (cypress version 2>/dev/null) || echo "not installed"
'

RAW=$(docker run --rm --entrypoint sh "$IMAGE" -c "$INNER_SCRIPT" 2>&1) || {
  echo "Could not run/inspect image: $IMAGE" >&2
  echo "$RAW" >&2
  exit 2
}

# Pulls the lines between "===NAME===" and the next marker (or EOF).
get_section() {
  printf '%s\n' "$RAW" | awk -v s="===$1===" '
    $0==s {flag=1; next}
    /^===.*===$/ {flag=0}
    flag {print}
  '
}

OS_INFO=$(get_section OS | tr '\n' ' ' | sed 's/"//g' | sed 's/  */ /g' | sed 's/ *$//')
NODE_VERSION=$(get_section NODE | head -1)
NPM_VERSION=$(get_section NPM | head -1)
PYTHON_VERSION=$(get_section PYTHON | head -1)
CYPRESS_RAW=$(get_section CYPRESS)

CYPRESS_PKG=$(printf '%s\n' "$CYPRESS_RAW" | grep -i "package version" | sed -E 's/.*: *//' || true)
CYPRESS_BIN=$(printf '%s\n' "$CYPRESS_RAW" | grep -i "binary version" | sed -E 's/.*: *//' || true)
[ -z "$CYPRESS_PKG" ] && CYPRESS_PKG="not installed"
[ -z "$CYPRESS_BIN" ] && CYPRESS_BIN="not installed"

# --- Compare against what the pipeline matrix / label claimed ---
MISMATCH=0
MISMATCH_NOTES=""

if [ -n "$EXPECTED_CYPRESS" ]; then
  case "$CYPRESS_PKG" in
    "$EXPECTED_CYPRESS"*) : ;;  # ok — matches on major(.minor) prefix
    *)
      MISMATCH=1
      MISMATCH_NOTES="${MISMATCH_NOTES}Cypress: expected ${EXPECTED_CYPRESS}.x, found ${CYPRESS_PKG}. "
      ;;
  esac
fi

if [ -n "$EXPECTED_NODE" ]; then
  case "$NODE_VERSION" in
    v"$EXPECTED_NODE"*|"$EXPECTED_NODE"*) : ;;
    *)
      MISMATCH=1
      MISMATCH_NOTES="${MISMATCH_NOTES}Node: expected ${EXPECTED_NODE}.x, found ${NODE_VERSION}. "
      ;;
  esac
fi

# --- Write JSON report (no jq dependency, just here to be portable) ---
MISMATCH_BOOL=false
[ "$MISMATCH" -eq 1 ] && MISMATCH_BOOL=true

cat > "$OUT_JSON" <<EOF
{
  "image": "$IMAGE",
  "os": "$OS_INFO",
  "node_version": "$NODE_VERSION",
  "npm_version": "$NPM_VERSION",
  "python_version": "$PYTHON_VERSION",
  "cypress_package_version": "$CYPRESS_PKG",
  "cypress_binary_version": "$CYPRESS_BIN",
  "expected_cypress_version": "${EXPECTED_CYPRESS:-null}",
  "expected_node_version": "${EXPECTED_NODE:-null}",
  "mismatch": $MISMATCH_BOOL
}
EOF

# --- Write Markdown report (nice for a PR comment or build artifact) ---
cat > "$OUT_MD" <<EOF
# Version audit: \`$IMAGE\`

| Component | Actual | Expected |
|---|---|---|
| OS | $OS_INFO | — |
| Node | $NODE_VERSION | ${EXPECTED_NODE:-—} |
| npm | $NPM_VERSION | — |
| Python | $PYTHON_VERSION | — |
| Cypress (package) | $CYPRESS_PKG | ${EXPECTED_CYPRESS:-—} |
| Cypress (binary) | $CYPRESS_BIN | — |

EOF

if [ "$MISMATCH" -eq 1 ]; then
  echo "**MISMATCH DETECTED:** $MISMATCH_NOTES" >> "$OUT_MD"
  echo "" >> "$OUT_MD"
  echo "MISMATCH: $MISMATCH_NOTES" >&2
  echo "Reports written to $OUT_JSON and $OUT_MD"
  exit 1
fi

echo "All checked versions match. Reports written to $OUT_JSON and $OUT_MD"
exit 0
