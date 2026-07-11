#!/usr/bin/env bash
# Report Test 10 - top-k output sweep. Fills Figure 9.
#
# No Locust and no CloudWatch needed: the handler already returns
# "inference_ms" in its JSON response body, so we read the number directly.
#
# Sends WARM sequential requests (one at a time) for each k, discarding the
# first few to exclude any cold start. Retrieval is a single dot product over
# 2000 x 384, so inference_ms should be essentially flat in k - confirming
# the transformer forward pass, not retrieval, is the bottleneck.
#
# Usage:  export HOST=... ; ./experiments/test10_topk.sh [onnx|pytorch]

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
OUT_DIR="$REPO_ROOT/data/raw"

if [ -z "${HOST:-}" ]; then
  echo "ERROR: \$HOST is not set." >&2
  exit 1
fi

VARIANT="${1:-onnx}"
ENDPOINT="${HOST}/${VARIANT}/search"
KS=(1 5 10 20 50 100)
REPS=20
WARMUP=3

mkdir -p "$OUT_DIR"
OUTFILE="${OUT_DIR}/topk_${VARIANT}_$(date -u +%Y%m%d_%H%M%S).csv"
echo "k,rep,inference_ms,client_ms,http_code" > "$OUTFILE"

QUERY="What were the primary economic, social, and political factors that led to the outbreak of World War I?"

echo "=== top-k sweep: $VARIANT | k in ${KS[*]} | $REPS reps each ==="

echo "Warming up ($WARMUP requests)..."
for _ in $(seq 1 $WARMUP); do
  curl -s -o /dev/null -X POST "$ENDPOINT" -H "Content-Type: application/json" \
    -d "{\"query\": \"$QUERY\", \"top_k\": 5}" --max-time 35 || true
  sleep 1
done

for k in "${KS[@]}"; do
  echo "  k=$k"
  for rep in $(seq 1 $REPS); do
    T0=$(date +%s%3N)
    BODY=$(curl -s -w '\n%{http_code}' -X POST "$ENDPOINT" \
      -H "Content-Type: application/json" \
      -d "{\"query\": \"$QUERY\", \"top_k\": $k}" --max-time 35 || echo -e "\n000")
    T1=$(date +%s%3N)

    CODE=$(printf '%s' "$BODY" | tail -n1)
    JSON=$(printf '%s' "$BODY" | sed '$d')
    INF=$(printf '%s' "$JSON" | python3 -c \
      'import sys,json;print(json.load(sys.stdin).get("inference_ms",""))' 2>/dev/null || echo "")

    echo "$k,$rep,$INF,$((T1 - T0)),$CODE" >> "$OUTFILE"
    sleep 0.3
  done
done

echo ""
echo "Done. $OUTFILE"
echo "Plot inference_ms (mean +/- std) against k for Figure 9."
