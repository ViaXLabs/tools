#!/usr/bin/env bash
# Snapshot everything relevant to AWS credential resolution at the point this
# script runs. Run this INSIDE a pipeline step that WORKS and again INSIDE
# one that FAILS, then diff the two outputs — that diff is usually the
# fastest route to root cause in a "some commands work, some don't" bug.
#
# Usage: ./00-env-snapshot.sh [profile]

set -uo pipefail

PROFILE="${1:-${AWS_PROFILE:-default}}"
OUT="/tmp/env-snapshot-$(date -u +%Y%m%dT%H%M%SZ).txt"

{
  echo "=== timestamp ==="
  date -u

  echo
  echo "=== identity running this script (host/container user, not AWS identity) ==="
  whoami 2>&1
  id 2>&1
  echo "HOME=$HOME"
  echo "PWD=$PWD"

  echo
  echo "=== which 'aws' is actually being invoked ==="
  command -v aws 2>&1
  type aws 2>&1
  aws --version 2>&1

  echo
  echo "=== all AWS_*/BOTO* env vars (these override everything in config files) ==="
  env | grep -Ei '^(AWS_|BOTO)' | sort

  echo
  echo "=== config/credentials file locations + presence ==="
  CFG="${AWS_CONFIG_FILE:-$HOME/.aws/config}"
  CREDS="${AWS_SHARED_CREDENTIALS_FILE:-$HOME/.aws/credentials}"
  echo "AWS_CONFIG_FILE resolves to: $CFG"
  ls -la "$CFG" 2>&1
  echo "AWS_SHARED_CREDENTIALS_FILE resolves to: $CREDS"
  ls -la "$CREDS" 2>&1

  echo
  echo "=== profile block for '$PROFILE' (secrets redacted, best-effort match) ==="
  grep -A 15 -E "^\[(profile )?$PROFILE\]" "$CFG" 2>/dev/null \
    | sed -E 's/(aws_secret_access_key|aws_session_token) *=.*/\1 = <redacted>/' \
    || echo "(no '[profile $PROFILE]' or '[$PROFILE]' block found in $CFG)"

  echo
  echo "=== aws configure list (shows the SOURCE of each field: env/config-file/etc) ==="
  aws configure list --profile "$PROFILE" 2>&1

  echo
  echo "=== non-CLI SDK / Go SDK / Terraform considerations ==="
  echo "AWS_SDK_LOAD_CONFIG=${AWS_SDK_LOAD_CONFIG:-<unset>}   (Go SDK v1 / Terraform ignore ~/.aws/config entirely unless this is '1')"
  command -v terraform >/dev/null 2>&1 && { echo "terraform present:"; terraform version 2>&1 | head -n1; }

  echo
  echo "=== container/instance credential sources (would silently override the profile) ==="
  echo "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI=${AWS_CONTAINER_CREDENTIALS_RELATIVE_URI:-<unset>}"
  echo "AWS_CONTAINER_CREDENTIALS_FULL_URI=${AWS_CONTAINER_CREDENTIALS_FULL_URI:-<unset>}"
  echo "AWS_WEB_IDENTITY_TOKEN_FILE=${AWS_WEB_IDENTITY_TOKEN_FILE:-<unset>}"
  if command -v curl >/dev/null 2>&1; then
    echo "-- IMDSv2 token probe (2s timeout; failing here is normal/expected off-EC2) --"
    curl -s -m 2 -X PUT "http://169.254.169.254/latest/api/token" \
      -H "X-aws-ec2-metadata-token-ttl-seconds: 21600" 2>&1
    echo
  fi
} | tee "$OUT"

echo
echo "Snapshot written to $OUT"
echo "Run this in your working step and your failing step, then: diff <(cat working.txt) <(cat failing.txt)"
