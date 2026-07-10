#!/usr/bin/env bash
# Report Test 1 - Cold start characterisation.
#
# Forces a TRUE cold start on every repetition by updating a dummy Lambda
# environment variable before each invocation. ANY config update invalidates
# all existing warm execution environments for that function - the next
# invocation is then guaranteed cold. This is standard serverless-benchmarking
# practice, not a hack: it measures the real cold-start cost deterministically,
# rather than waiting N minutes and hoping AWS happened to reclaim the
# container by then (which is unpredictable and can make a 900s wait either
# unnecessarily long, or - if AWS's real reclaim window is even longer -
# still wrong).
#
# This means NO multi-minute sleeps are needed. 10 reps complete in a few
# minutes instead of ~2.5 hours.
#
# Each row's "forced_cold" column is always 1. Cross-check against
# CloudWatch's own cold_start column (from pull_cloudwatch.py) after
# collection - if any row shows cold_start=0 there, that specific
# invocation somehow landed on a warm container despite the forced update
# (rare, but possible under a race) and should be excluded from the average.
#
# Usage:
#   ./cold_start_test.sh <onnx|pytorch> [num_requests]
#
# Example (still 10 reps, now ~3-8 min instead of ~2.5h):
#   ./cold_start_test.sh pytorch 10

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
OUT_DIR="$REPO_ROOT/data/raw"

if [ -z "${HOST:-}" ]; then
  echo "ERROR: \$HOST is not set." >&2
  exit 1
fi

VARIANT="${1:?Usage: cold_start_test.sh <onnx|pytorch> [num_requests]}"
NUM="${2:-10}"

case "$VARIANT" in
  onnx)    FN_VAR="ONNX_FN" ;;
  pytorch) FN_VAR="PT_FN" ;;
  *) echo "ERROR: variant must be 'onnx' or 'pytorch'" >&2; exit 1 ;;
esac

FN_NAME="${!FN_VAR:-}"
if [ -z "$FN_NAME" ]; then
  echo "ERROR: \$$FN_VAR is not set. source ~/minilm-env.sh first (or run on your laptop, not EC2 - this script calls the AWS CLI directly)." >&2
  exit 1
fi

ENDPOINT="${HOST}/${VARIANT}/search"
mkdir -p "$OUT_DIR"
STAMP=$(date -u +%Y%m%d_%H%M%S)
OUTFILE="${OUT_DIR}/cold_start_${VARIANT}_${STAMP}.csv"
WINDOW="${OUT_DIR}/cold_start_${VARIANT}_${STAMP}_window.json"

echo "request_num,timestamp_utc,http_code,client_ms,forced_cold" > "$OUTFILE"

START_TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
echo "=== Cold start (forced): $VARIANT | $NUM requests | function=$FN_NAME ==="

for i in $(seq 1 "$NUM"); do
  # Force invalidation of any existing warm environment
  CACHE_BUST="${i}-$(date +%s)-$RANDOM"
  aws lambda update-function-configuration \
    --function-name "$FN_NAME" \
    --environment "Variables={CACHE_BUST=$CACHE_BUST}" \
    --region us-east-1 > /dev/null

  # Wait for the config update to actually apply
  for _ in $(seq 1 15); do
    STATUS=$(aws lambda get-function-configuration --function-name "$FN_NAME" \
      --region us-east-1 --query "LastUpdateStatus" --output text)
    [ "$STATUS" = "Successful" ] && break
    sleep 2
  done
  if [ "$STATUS" != "Successful" ]; then
    echo "  WARNING: update did not confirm Successful (status=$STATUS) - invoking anyway"
  fi

  TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  T0=$(python3 -c 'import time; print(int(time.time()*1000))')
  CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$ENDPOINT" \
      -H "Content-Type: application/json" \
      -d '{"query": "Who invented the telephone?", "top_k": 5}' \
      --max-time 65 || echo "000")
  T1=$(python3 -c 'import time; print(int(time.time()*1000))')
  MS=$((T1 - T0))

  echo "$i,$TS,$CODE,$MS,1" >> "$OUTFILE"
  printf "  [%2d/%2d] %s  HTTP %s  %s ms\n" "$i" "$NUM" "$TS" "$CODE" "$MS"

  sleep 3   # brief buffer between rounds, not for cold-start purposes
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
echo "Next (laptop, lab session active):"
echo "  python3 analysis/pull_cloudwatch.py --window $WINDOW --function $FN_NAME"
echo "  -> cross-check the cold_start column: should be 1 for every row."