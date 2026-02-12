#!/bin/bash
set -euo pipefail

# Usage:
#   ./make_apply.sh dry
#   ./make_apply.sh real
# Optional filters:
#   ./make_apply.sh dry filters.json
#   ./make_apply.sh real filters.json
#
# Outputs:
#   apply_log.csv

MODE="${1:-}"
FILTERS="${2:-}"

if [[ "${MODE}" != "dry" && "${MODE}" != "real" ]]; then
  echo "Usage: $0 <dry|real> [filters.json]"
  exit 1
fi

if [[ "${MODE}" == "dry" ]]; then
  echo "== APPLY DRY-RUN =="
  if [[ -n "${FILTERS}" ]]; then
    python3 apply_newrelic_tag_changes.py \
      --report tag_report.json \
      --policy tag_policy.json \
      --filters "${FILTERS}" \
      --out-csv apply_log.csv \
      --dry-run
  else
    python3 apply_newrelic_tag_changes.py \
      --report tag_report.json \
      --policy tag_policy.json \
      --out-csv apply_log.csv \
      --dry-run
  fi
else
  echo "== APPLY REAL (ADD only) =="
  if [[ -n "${FILTERS}" ]]; then
    python3 apply_newrelic_tag_changes.py \
      --report tag_report.json \
      --policy tag_policy.json \
      --filters "${FILTERS}" \
      --out-csv apply_log.csv
  else
    python3 apply_newrelic_tag_changes.py \
      --report tag_report.json \
      --policy tag_policy.json \
      --out-csv apply_log.csv
  fi
fi

echo "Done. Review apply_log.csv"
