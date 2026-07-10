#!/usr/bin/env bash
# Runs one Locust experiment headless and writes a sidecar _window.json
# recording the exact UTC start/end. analysis/pull_cloudwatch.py reads that
# window to fetch exactly the matching CloudWatch REPORT lines.
#
# Requires $HOST (API Gateway base URL, no path):
#   export HOST="https://xxxxxxxxxx.execute-api.us-east-1.amazonaws.com"
#
# Usage:
#   ./run_experiment.sh <burst|shaped> <name> [extra locust args...]
#
# Examples:
#   VARIANT=onnx ./run_experiment.sh burst burst_onnx_n10_run1 -u 10 -r 10 -t 30s
#   VARIANT=onnx PEAK_USERS=25 SPAWN_RATE=5 ./run_experiment.sh shaped steady_onnx_p25_s5_run1

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
OUT_DIR="$REPO_ROOT/data/raw"

if [ -z "${HOST:-}" ]; then
  echo "ERROR: \$HOST is not set." >&2
  echo "  export HOST=\"https://<api-id>.execute-api.us-east-1.amazonaws.com\"" >&2
  exit 1
fi

MODE="${1:?Usage: run_experiment.sh <burst|shaped> <name> [locust args...]}"
NAME="${2:?Usage: run_experiment.sh <burst|shaped> <name> [locust args...]}"
shift 2

case "$MODE" in
  burst)  LOCUSTFILE="locustfile_burst.py" ;;
  shaped) LOCUSTFILE="locustfile_shaped.py" ;;
  *) echo "ERROR: unknown mode '$MODE' (use 'burst' or 'shaped')" >&2; exit 1 ;;
esac

mkdir -p "$OUT_DIR"
PREFIX="$OUT_DIR/${NAME}"

# cd so locust can import common.py as a sibling module
cd "$SCRIPT_DIR"

START_TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
echo "--- [$NAME] mode=$MODE variant=${VARIANT:-onnx} bucket=${QUESTION_BUCKET:-all} start=$START_TS"

locust -f "$LOCUSTFILE" --host "$HOST" --headless --only-summary \
       --csv "$PREFIX" "$@"

END_TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)

cat > "${PREFIX}_window.json" <<EOF
{
  "name": "$NAME",
  "mode": "$MODE",
  "variant": "${VARIANT:-onnx}",
  "bucket": "${QUESTION_BUCKET:-all}",
  "top_k": ${TOP_K:-5},
  "start": "$START_TS",
  "end": "$END_TS"
}
EOF

echo "--- [$NAME] end=$END_TS  ->  ${PREFIX}_stats.csv + ${PREFIX}_window.json"
