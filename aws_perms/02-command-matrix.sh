#!/usr/bin/env bash
# Turn "some commands work, some don't" into a concrete, categorized list
# instead of an impression. Edit the CMDS array to match/extend commands you
# actually run in the pipeline (these are read-only by design).
#
# Usage: ./02-command-matrix.sh [profile]

set -uo pipefail

PROFILE="${1:-${AWS_PROFILE:-default}}"
LOG="/tmp/command-matrix-$(date -u +%Y%m%dT%H%M%SZ).log"

CMDS=(
  "sts get-caller-identity"
  "sts get-session-token"
  "iam get-user"
  "s3 ls"
  "ec2 describe-regions"
  "ec2 describe-instances --max-results 5"
  "secretsmanager list-secrets --max-results 5"
  "ssm describe-parameters --max-results 5"
  "ecr describe-repositories --max-results 5"
  "logs describe-log-groups --limit 5"
)

{
  printf "%-50s %-6s %s\n" "COMMAND" "RESULT" "ERROR (first line)"
  printf '%.0s-' {1..100}; echo
} | tee "$LOG"

for c in "${CMDS[@]}"; do
  # shellcheck disable=SC2086
  err=$(aws --profile "$PROFILE" $c 2>&1 1>/dev/null)
  rc=$?
  if [ $rc -eq 0 ]; then
    printf "%-50s %-6s %s\n" "$c" "PASS" "" | tee -a "$LOG"
  else
    firstline=$(echo "$err" | head -n1)
    printf "%-50s %-6s %s\n" "$c" "FAIL" "$firstline" | tee -a "$LOG"
  fi
done

{
  echo
  echo "=== auto-categorized failures ==="
  echo "-- likely credential RESOLUTION issue (profile/credential_process, not IAM) --"
  grep -iE "could not be found|unable to locate credentials|no such profile" "$LOG" || echo "  (none)"
  echo "-- likely PERMISSIONS issue (feed these into 03-permission-simulate.sh) --"
  grep -iE "AccessDenied|UnauthorizedOperation|not authorized" "$LOG" || echo "  (none)"
  echo "-- likely STALE/EXPIRED credentials --"
  grep -iE "ExpiredToken|InvalidClientTokenId|token.*expired" "$LOG" || echo "  (none)"
} | tee -a "$LOG"

echo
echo "Full log: $LOG"
