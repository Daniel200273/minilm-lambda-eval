#!/usr/bin/env bash
# Report Test 1 - Cold start characterisation.
#
# Deliberately NOT a Locust test: we need multi-minute gaps between single
# requests so AWS reclaims the container each time. Locust is not built for
# that. Plain curl in a sleep loop is the right tool.
#
# AWS reclaims idle Lambda containers after roughly 5-15 minutes (undocumented
# and variable). 900 s matches Giorgia's methodology; 300 s is a pragmatic
# compromise if you are short on lab time - but note in the report which you used.
#
# The client-side timing captured here INCLUDES network + API Gateway. The
# authoritative InitDuration comes from CloudWatch afterwards; use the
# timestamps in this CSV as the window.
#
# Usage:
#   ./cold_start_test.sh <onnx|pytorch> <num_requests> <gap_seconds>
#
# Example (report methodology, ~2.5 h for 10 requests):
#   ./cold_start_test.sh onnx 10 900

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
OUT_DIR="$REPO_ROOT/data/raw"

if [ -z "${HOST:-}" ]; then
  echo "ERROR: \$HOST is not set." >&2
  exit 1
fi

VARIANT="${1:?Usage: cold_start_test.sh <onnx|pytorch> [num_requests] [gap_seconds]}"
NUM="${2:-10}"
GAP="${3:-900}"

case "$VARIANT" in
  onnx|pytorch) ;;
  *) echo "ERROR: variant must be 'onnx' or 'pytorch'" >&2; exit 1 ;;
esac

ENDPOINT="${HOST}/${VARIANT}/search"
mkdir -p "$OUT_DIR"
STAMP=$(date -u +%Y%m%d_%H%M%S)
OUTFILE="${OUT_DIR}/cold_start_${VARIANT}_${STAMP}.csv"
WINDOW="${OUT_DIR}/cold_start_${VARIANT}_${STAMP}_window.json"

echo "request_num,timestamp_utc,http_code,client_ms" > "$OUTFILE"

START_TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
echo "=== Cold start: $VARIANT | $NUM requests | ${GAP}s gaps | ~$((NUM * GAP / 60)) min total ==="

for i in $(seq 1 "$NUM"); do
  TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  T0=$(date +%s%3N)
  CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$ENDPOINT" \
      -H "Content-Type: application/json" \
      -d '{"query": "Who invented the telephone?", "top_k": 5}' \
      --max-time 35 || echo "000")
  T1=$(date +%s%3N)
  MS=$((T1 - T0))

  echo "$i,$TS,$CODE,$MS" >> "$OUTFILE"
  printf "  [%2d/%2d] %s  HTTP %s  %s ms\n" "$i" "$NUM" "$TS" "$CODE" "$MS"

  if [ "$i" -lt "$NUM" ]; then
    echo "         sleeping ${GAP}s so the container goes cold..."
    sleep "$GAP"
  fi
done

END_TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
cat > "$WINDOW" <<EOF
{
  "name": "cold_start_${VARIANT}_${STAMP}",
  "mode": "cold_start",
  "variant": "$VARIANT",
  "start": "$START_TS",
  "end": "$END_TS"
}
EOF

echo ""
echo "Done. $OUTFILE"
echo "Next (on your laptop, lab session active):"
echo "  python3 analysis/pull_cloudwatch.py --window $WINDOW --function <${VARIANT}-function-name>"
echo "  -> the init_duration_ms column is what Table 3 needs."
