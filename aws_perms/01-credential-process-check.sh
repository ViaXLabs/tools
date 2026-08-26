#!/usr/bin/env bash
# Validate your credential_process script's output shape (Version,
# AccessKeyId, SecretAccessKey, SessionToken, Expiration) and run it
# repeatedly to catch intermittent/flaky output — fits the "detected in
# certain circumstances" symptom.
#
# Usage: ./01-credential-process-check.sh '<command that runs your refresh script>' [iterations]
# Example: ./01-credential-process-check.sh './aws-cred-refresh.sh --profile ci' 5
#
# Requires: jq

set -uo pipefail

CMD="${1:?Usage: $0 '<credential_process command>' [iterations]}"
ITER="${2:-5}"

pass=0
fail=0

for i in $(seq 1 "$ITER"); do
  echo "--- run $i/$ITER ---"
  out="$(eval "$CMD" 2>"/tmp/cred-stderr-$i.log")"
  rc=$?

  if [ -s "/tmp/cred-stderr-$i.log" ]; then
    echo "  [WARN] stderr was non-empty (SDKs can capture/log this — make sure it's not a secret):"
    sed 's/^/    /' "/tmp/cred-stderr-$i.log"
  fi

  if [ $rc -ne 0 ]; then
    echo "  [FAIL] non-zero exit code: $rc"
    fail=$((fail + 1))
    continue
  fi

  if ! echo "$out" | jq empty >/dev/null 2>&1; then
    echo "  [FAIL] stdout is not valid JSON:"
    echo "$out" | sed 's/^/    /'
    fail=$((fail + 1))
    continue
  fi

  version=$(echo "$out" | jq -r '.Version // empty')
  akid=$(echo "$out" | jq -r '.AccessKeyId // empty')
  secret=$(echo "$out" | jq -r '.SecretAccessKey // empty')
  expiration=$(echo "$out" | jq -r '.Expiration // empty')

  missing=""
  [ "$version" = "1" ] || missing="$missing Version(got:'$version')"
  [ -n "$akid" ] || missing="$missing AccessKeyId"
  [ -n "$secret" ] || missing="$missing SecretAccessKey"
  [ -n "$expiration" ] || missing="$missing Expiration"

  if [ -n "$missing" ]; then
    echo "  [FAIL] required field(s) missing/invalid:$missing"
    fail=$((fail + 1))
    continue
  fi

  # Expiration must parse and be in the future (assumes GNU date; on
  # Alpine/busybox images install coreutils or adapt this check).
  now_epoch=$(date -u +%s)
  exp_epoch=$(date -u -d "$expiration" +%s 2>/dev/null)
  if [ -z "$exp_epoch" ]; then
    echo "  [FAIL] Expiration '$expiration' did not parse as a date"
    fail=$((fail + 1))
    continue
  fi
  remaining=$((exp_epoch - now_epoch))
  if [ "$remaining" -le 0 ]; then
    echo "  [FAIL] Expiration '$expiration' is already in the past (${remaining}s)"
    fail=$((fail + 1))
    continue
  fi

  echo "  [PASS] AccessKeyId=${akid:0:6}... expires in ${remaining}s ($expiration)"
  pass=$((pass + 1))
done

echo
echo "=== summary: $pass passed, $fail failed (of $ITER runs) ==="
[ "$fail" -eq 0 ]
