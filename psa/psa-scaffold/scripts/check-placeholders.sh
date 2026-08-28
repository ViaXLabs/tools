#!/usr/bin/env bash
# scripts/check-placeholders.sh
#
# Finds every REPLACE_ME left in the repo and prints file:line for each.
# Run this from the repo root after filling in tfvars/pipeline values, or
# as a mechanical "is this actually done" check before handing PSA off.
#
# Exit code 0 = clean (no placeholders found). Exit code 1 = found some,
# listed below. Safe to wire into CI as a gate if you want one.
#
# Usage:
#   ./scripts/check-placeholders.sh
#   ./scripts/check-placeholders.sh terraform/live/dev   # scope to one dir

set -euo pipefail

SCOPE="${1:-.}"

echo "Scanning '$SCOPE' for REPLACE_ME ..."
echo

MATCHES=$(grep -rIn "REPLACE_ME" "$SCOPE" \
  --include="*.tf" \
  --include="*.tfvars" \
  --include="*.yaml" \
  --include="*.yml" \
  --include="*.md" \
  2>/dev/null || true)

if [ -z "$MATCHES" ]; then
  echo "No REPLACE_ME placeholders found. Clean."
  exit 0
else
  echo "$MATCHES"
  echo
  COUNT=$(echo "$MATCHES" | wc -l)
  echo "Found $COUNT placeholder(s) above -- each one needs a real value before this will work."
  exit 1
fi
