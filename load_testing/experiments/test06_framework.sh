#!/usr/bin/env bash
# Report Test 6 - Framework performance comparison. Fills Figure 4.
#
# 50 concurrent users, 3 minutes sustained, both variants, 3 repetitions.
# This is the headline ONNX-vs-PyTorch number.
#
# NOTE: with ReservedConcurrentExecutions = 10, 50 sustained users will
# saturate the PyTorch function (~700 ms/req => ~35 concurrent needed) and
# produce heavy throttling, while ONNX (~25 ms/req => ~1.3 concurrent needed)
# will barely touch the limit. That asymmetry is a genuine finding, not a bug.
# Report the AvgT of *successful* invocations alongside the failure rate -
# CloudWatch Duration only counts invocations that actually ran.
#
# Runtime: 2 variants x 3 reps x 3 min ~= 20 min.
#
# Usage:  export HOST=... ; ./experiments/test06_framework.sh

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNNER="$SCRIPT_DIR/../run_experiment.sh"

REPS=3

for variant in onnx pytorch; do
  for rep in $(seq 1 $REPS); do
    VARIANT="$variant" \
    PEAK_USERS=50 \
    SPAWN_RATE=10 \
    RAMP_SECONDS=10 \
    HOLD_SECONDS=180 \
    RPS_PER_USER=1.0 \
      "$RUNNER" shaped "framework_${variant}_50users_run${rep}"
    sleep 30   # longer settle: let throttled containers drain
  done
done

echo "Test 6 complete."
