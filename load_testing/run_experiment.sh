#!/usr/bin/env bash
# Runs a locustfile and saves the exact UTC start/end time to a sidecar JSON
# file, so analysis/pull_cloudwatch.py can fetch exactly the right log window.
#
# Requires $HOST (API Gateway base URL, no path).
#
# Usage:
#   ./run_experiment.sh <burst|shaped> <name> [extra locust args...]

set -uo pipefail
# NOTE: deliberately NOT using -e for the whole script. Locust exits non-zero
# whenever a run has ANY failed requests - which is the EXPECTED, WANTED
# result for burst/steady tests above the concurrency limit, not an error.
# Under -e that exit code would kill this script before it ever wrote
# _window.json, silently truncating every test campaign at the first N value
# with real failures. The `|| true` below is what fixes that.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
OUT_DIR="$REPO_ROOT/data/raw"

if [ -z "${HOST:-}" ]; then
  echo "Error: \$HOST is not set." >&2
  exit 1
fi

MODE="${1:?Usage: run_experiment.sh <burst|shaped> <name> [locust args...]}"
NAME="${2:?Usage: run_experiment.sh <burst|shaped> <name> [locust args...]}"
shift 2

case "$MODE" in
  burst)  LOCUSTFILE="locustfile_burst.py" ;;
  shaped) LOCUSTFILE="locustfile_shaped.py" ;;
  *) echo "Unknown mode: $MODE (use 'burst' or 'shaped')"; exit 1 ;;
esac

mkdir -p "$OUT_DIR"
CSV_PREFIX="$OUT_DIR/${NAME}"

cd "$SCRIPT_DIR"

START_TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
echo "[$NAME] mode=$MODE variant=${VARIANT:-onnx} start=$START_TS"

locust -f "$LOCUSTFILE" --host "$HOST" --headless --only-summary \
       --csv "$CSV_PREFIX" "$@" || true
# ^ `|| true`: a non-zero exit here means "the test ran and recorded
# failures," not "the test itself broke." We still want window.json written
# and the calling script to continue to the next run either way.

END_TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
echo "[$NAME] end=$END_TS"

cat > "${CSV_PREFIX}_window.json" <<EOF
{
  "name": "$NAME",
  "mode": "$MODE",
  "variant": "${VARIANT:-onnx}",
  "start": "$START_TS",
  "end": "$END_TS"
}
EOF

echo "Window saved: ${CSV_PREFIX}_window.json"