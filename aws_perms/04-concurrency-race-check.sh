#!/usr/bin/env bash
# The SDK does NOT cache credential_process output itself — any caching or
# locking has to be implemented in your script. If it isn't, concurrent
# pipeline steps (common in Docker/Harness parallel stages) hitting the same
# refresh script can race and produce inconsistent or corrupted output. This
# fires N parallel invocations to test that directly.
#
# Usage: ./04-concurrency-race-check.sh '<credential_process command>' [parallelism]
#
# Requires: jq

set -uo pipefail

CMD="${1:?Usage: $0 '<credential_process command>' [parallelism]}"
N="${2:-8}"

TMPDIR=$(mktemp -d)
echo "Firing $N parallel invocations of: $CMD"
echo "Output captured in $TMPDIR"

pids=()
for i in $(seq 1 "$N"); do
  ( eval "$CMD" >"$TMPDIR/out-$i.json" 2>"$TMPDIR/err-$i.log" ) &
  pids+=("$!")
done
for pid in "${pids[@]}"; do wait "$pid"; done

echo
echo "=== distinct AccessKeyIds returned across $N parallel runs ==="
for f in "$TMPDIR"/out-*.json; do
  jq -r '.AccessKeyId // "PARSE_ERROR"' "$f" 2>/dev/null
done | sort | uniq -c

echo
echo "=== runs that failed to produce valid JSON ==="
bad=0
for f in "$TMPDIR"/out-*.json; do
  if ! jq empty "$f" >/dev/null 2>&1; then
    echo "  $f:"
    sed 's/^/    /' "$f"
    bad=$((bad + 1))
  fi
done
[ "$bad" -eq 0 ] && echo "  (none — all $N runs produced valid JSON)"

echo
echo "=== stderr output across runs (watch for lock/file-write conflicts) ==="
any_err=0
for f in "$TMPDIR"/err-*.log; do
  if [ -s "$f" ]; then
    echo "  $f:"
    sed 's/^/    /' "$f"
    any_err=1
  fi
done
[ "$any_err" -eq 0 ] && echo "  (none)"

echo
echo "Kept in $TMPDIR for further inspection."
