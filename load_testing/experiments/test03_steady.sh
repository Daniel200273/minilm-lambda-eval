#!/usr/bin/env bash
# Report Test 3 - Steady traffic. Fills Table 5 (and feeds Tables 6 & 8).
#
# Three trapezoidal shapes matching the report:
#     peak 25 req/s, step 5
#     peak 50 req/s, step 10
#     peak 50 req/s, step 5
# 5 repetitions each. Each run is 2*RAMP + HOLD seconds.
#
# Because wait_time = constant_throughput(1.0), PEAK_USERS == target req/s.
# SPAWN_RATE is the report's "step size".
#
# Table 5 in the report is ONNX-only, so that is the default. Pass "pytorch"
# to gather the same data for the other variant (worth doing - see note in
# the guide about how differently the two behave under sustained load).
#
# Runtime: 3 configs x 5 reps x 60s ~= 20 min per variant (incl. teardown).
#
# Usage:
#   export HOST=...
#   ./experiments/test03_steady.sh           # onnx
#   ./experiments/test03_steady.sh pytorch

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNNER="$SCRIPT_DIR/../run_experiment.sh"

VARIANT_ARG="${1:-onnx}"
REPS=5

# "peak:step" pairs
CONFIGS=("25:5" "50:10" "50:5")

for cfg in "${CONFIGS[@]}"; do
  PEAK="${cfg%%:*}"
  STEP="${cfg##*:}"
  for rep in $(seq 1 $REPS); do
    VARIANT="$VARIANT_ARG" \
    PEAK_USERS="$PEAK" \
    SPAWN_RATE="$STEP" \
    RAMP_SECONDS=15 \
    HOLD_SECONDS=30 \
    RPS_PER_USER=1.0 \
      "$RUNNER" shaped "steady_${VARIANT_ARG}_p${PEAK}_s${STEP}_run${rep}"
    sleep 10
  done
done

echo "Test 3 complete."
