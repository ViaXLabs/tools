#!/bin/bash
#
# tf-unlock-s3.sh
#
# Checks and (optionally) clears a Terraform native S3 state lock (.tflock file).
# Works with Terraform's `use_lockfile = true` S3 backend locking (Terraform 1.10+).
#
# This does NOT touch DynamoDB-based locks (dynamodb_table backend arg) — this
# is specifically for the newer S3-native lockfile mechanism.
#
# Usage:
#   ./tf-unlock-s3.sh <bucket> <state-key> [max-age-minutes] [--force]
#
# Examples:
#   ./tf-unlock-s3.sh my-tf-bucket prod/infrastructure/terraform.tfstate
#   ./tf-unlock-s3.sh my-tf-bucket prod/infrastructure/terraform.tfstate 30
#   ./tf-unlock-s3.sh my-tf-bucket prod/infrastructure/terraform.tfstate 30 --force
#
# Arguments:
#   bucket           - S3 bucket name holding your terraform state
#   state-key        - Full key/path to your .tfstate file (NOT including .tflock)
#   max-age-minutes  - (optional) Only auto-delete if lock is older than this many
#                       minutes. Default: 15. Set to 0 to skip the age check entirely.
#   --force          - Skip the interactive confirmation prompt.
#
# Exit codes:
#   0 - success (lock deleted, or no lock found)
#   1 - usage error
#   2 - lock exists but is too recent to auto-clear (safety stop)
#   3 - user declined confirmation
#   4 - AWS CLI error

set -euo pipefail

BUCKET="${1:-}"
STATE_KEY="${2:-}"
MAX_AGE_MINUTES="${3:-15}"
FORCE_FLAG="${4:-}"

if [[ -z "$BUCKET" || -z "$STATE_KEY" ]]; then
  echo "Usage: $0 <bucket> <state-key> [max-age-minutes] [--force]" >&2
  echo "Example: $0 my-tf-bucket prod/infrastructure/terraform.tfstate 30 --force" >&2
  exit 1
fi

LOCK_KEY="${STATE_KEY}.tflock"

echo "Checking for lock file:"
echo "  s3://${BUCKET}/${LOCK_KEY}"
echo ""

# Check if the lock file exists
if ! aws s3api head-object --bucket "$BUCKET" --key "$LOCK_KEY" >/tmp/tf-lock-head.json 2>/tmp/tf-lock-err.txt; then
  if grep -qi "Not Found\|404" /tmp/tf-lock-err.txt; then
    echo "✅ No lock file found. Nothing to do — state is not locked."
    exit 0
  else
    echo "❌ AWS CLI error while checking lock:" >&2
    cat /tmp/tf-lock-err.txt >&2
    exit 4
  fi
fi

# Pull last-modified time from the head-object response
LAST_MODIFIED=$(grep -o '"LastModified": *"[^"]*"' /tmp/tf-lock-head.json | sed 's/.*: *"//; s/"$//')

if [[ -z "$LAST_MODIFIED" ]]; then
  echo "⚠️  Found a lock file but couldn't parse its LastModified timestamp."
  echo "Raw head-object output:"
  cat /tmp/tf-lock-head.json
else
  LOCK_EPOCH=$(date -d "$LAST_MODIFIED" +%s 2>/dev/null || date -jf "%Y-%m-%dT%H:%M:%SZ" "$LAST_MODIFIED" +%s 2>/dev/null || echo "")
  NOW_EPOCH=$(date +%s)

  if [[ -n "$LOCK_EPOCH" ]]; then
    AGE_MINUTES=$(( (NOW_EPOCH - LOCK_EPOCH) / 60 ))
    echo "🔒 Lock file found."
    echo "  Last modified: $LAST_MODIFIED"
    echo "  Age: ${AGE_MINUTES} minute(s)"
    echo ""
  else
    echo "⚠️  Lock file found, but couldn't calculate its age (date parsing failed)."
    echo "  Last modified (raw): $LAST_MODIFIED"
    AGE_MINUTES=""
  fi
fi

# Try to show WHO holds the lock / what operation, if the lock file is JSON
echo "Lock contents (who/what/when):"
aws s3 cp "s3://${BUCKET}/${LOCK_KEY}" - 2>/dev/null | cat || echo "  (couldn't read lock file contents)"
echo ""
echo "---"
echo ""

# Age-based safety check
if [[ "$MAX_AGE_MINUTES" != "0" && -n "${AGE_MINUTES:-}" ]]; then
  if (( AGE_MINUTES < MAX_AGE_MINUTES )); then
    echo "🛑 Lock is only ${AGE_MINUTES} minute(s) old (threshold: ${MAX_AGE_MINUTES})."
    echo "This might be an ACTIVE run, not a stale lock. Not deleting automatically."
    echo "If you're sure it's stale, re-run with a lower threshold, e.g.:"
    echo "  $0 $BUCKET $STATE_KEY 0 --force"
    exit 2
  fi
fi

# Confirmation, unless --force was passed
if [[ "$FORCE_FLAG" != "--force" ]]; then
  read -r -p "Delete this lock file now? [y/N] " CONFIRM
  if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
    echo "Aborted. Lock file NOT deleted."
    exit 3
  fi
fi

echo "Deleting lock file..."
aws s3 rm "s3://${BUCKET}/${LOCK_KEY}"
echo "✅ Lock cleared. Terraform should be able to run again."
