#!/usr/bin/env bash
# Report Test 7 - Vertical scaling. Fills Figures 5 and 6.
#
# This test CANNOT be fully automated from EC2, because changing Lambda memory
# requires a `sam deploy` from your laptop (EC2 has no AWS credentials, by
# design). It is a coordinated loop:
#
#   ON LAPTOP:  sam deploy --parameter-overrides "OnnxMemorySize=1024 PytorchMemorySize=1024"
#   ON EC2:     ./experiments/test07_vertical_scaling.sh 1024
#   ON LAPTOP:  sam deploy --parameter-overrides "OnnxMemorySize=2048 PytorchMemorySize=2048"
#   ON EC2:     ./experiments/test07_vertical_scaling.sh 2048
#   ON LAPTOP:  sam deploy --parameter-overrides "OnnxMemorySize=3008 PytorchMemorySize=3008"
#   ON EC2:     ./experiments/test07_vertical_scaling.sh 3008
#
# The MEM argument is only used to LABEL the output files - it does not change
# anything on AWS. Passing the wrong value silently mislabels your data, so
# double-check the deployed memory first:
#
#   aws lambda get-function-configuration --function-name <fn> \
#       --query MemorySize --region us-east-1
#
# WARNING (from template.yaml's own comments): the ONNX function times out at
# 1024 MB on a COLD start, because Lambda scales vCPU with memory. Warm
# invocations are fine. Let both endpoints warm up before each sweep, and
# expect cold-start failures at the lowest tier - that is itself a result.
#
# Runtime: ~6 min per memory tier (both variants, 3 reps).

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNNER="$SCRIPT_DIR/../run_experiment.sh"

MEM="${1:?Usage: test07_vertical_scaling.sh <1024|2048|3008>  (label only - deploy separately)}"
case "$MEM" in
  1024|2048|3008) ;;
  *) echo "ERROR: memory label must be 1024, 2048 or 3008" >&2; exit 1 ;;
esac

if [ -z "${HOST:-}" ]; then echo "ERROR: \$HOST not set" >&2; exit 1; fi

REPS=3

# Warm both endpoints so the sweep measures steady-state compute, not cold start.
echo "Warming endpoints..."
for variant in onnx pytorch; do
  for _ in 1 2 3; do
    curl -s -o /dev/null -X POST "${HOST}/${variant}/search" \
      -H "Content-Type: application/json" \
      -d '{"query": "warmup", "top_k": 5}' --max-time 35 || true
    sleep 1
  done
done

for variant in onnx pytorch; do
  for rep in $(seq 1 $REPS); do
    VARIANT="$variant" \
    PEAK_USERS=10 \
    SPAWN_RATE=5 \
    RAMP_SECONDS=10 \
    HOLD_SECONDS=60 \
    RPS_PER_USER=1.0 \
      "$RUNNER" shaped "vscale_${variant}_mem${MEM}_run${rep}"
    sleep 10
  done
done

echo "Test 7 (memory=${MEM} MiB) complete."
echo "Remember to redeploy at the next memory tier from your laptop before continuing."
