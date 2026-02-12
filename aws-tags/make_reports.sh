#!/bin/bash
set -euo pipefail

# Usage:
#   ./make_reports.sh
#   ./make_reports.sh 1234567
#   ./make_reports.sh 1234567 filters.json
#
# Uses NR_ACCOUNT_ID if you don't provide an account id.
#
# Outputs:
#   entities_tags.json
#   tag_report.json
#   tag_report.csv
#   tag_report_wide_required.csv
#   tag_report_wide_all.csv

ACCOUNT_ID="${1:-}"
FILTERS="${2:-}"

if [[ -z "${ACCOUNT_ID}" ]]; then
  if [[ -n "${NR_ACCOUNT_ID:-}" ]]; then
    ACCOUNT_ID="${NR_ACCOUNT_ID}"
  fi
fi

if [[ -z "${ACCOUNT_ID}" ]]; then
  echo "Usage: $0 [account-id] [filters.json]"
  echo "Or set: export NR_ACCOUNT_ID=1234567"
  exit 1
fi

echo "== Export =="
if [[ -n "${FILTERS}" ]]; then
  python3 export_newrelic_entity_tags.py --account-id "${ACCOUNT_ID}" --out entities_tags.json --filters "${FILTERS}"
else
  python3 export_newrelic_entity_tags.py --account-id "${ACCOUNT_ID}" --out entities_tags.json
fi

echo "== Check (writes CSV + wide REQUIRED + wide ALL) =="
if [[ -n "${FILTERS}" ]]; then
  python3 check_newrelic_tags.py \
    --in entities_tags.json \
    --policy tag_policy.json \
    --filters "${FILTERS}" \
    --out-json tag_report.json \
    --out-csv tag_report.csv \
    --only-action-needed
else
  python3 check_newrelic_tags.py \
    --in entities_tags.json \
    --policy tag_policy.json \
    --out-json tag_report.json \
    --out-csv tag_report.csv \
    --only-action-needed
fi

echo "Done."
echo "Review:"
echo "  - tag_report.csv"
echo "  - tag_report_wide_required.csv"
echo "  - tag_report_wide_all.csv"
