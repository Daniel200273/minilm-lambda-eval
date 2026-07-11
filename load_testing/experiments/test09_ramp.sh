#!/usr/bin/env bash
# Report Test 9 - Cold-start ramp-up visualisation. Fills Figure 8.
#
# 0 -> 20 users over 60 s, hold 5 min, ramp down. One run per variant is
# enough: the deliverable is a time-series plot, not an averaged table.
#
# IMPORTANT: the function must be COLD when this starts, otherwise there is
# no ramp-up spike to visualise. Leave the endpoint idle for ~15 min before
# running, or run this first thing in a session.
#
# The per-second time series comes from <name>_stats_history.csv, which
# --csv writes automatically. That is the file the plot needs.
#
# Runtime: ~7 min per variant.
#
# Usage:  export HOST=... ; ./experiments/test09_ramp.sh [onnx|pytorch]

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNNER="$SCRIPT_DIR/../run_experiment.sh"

if [ $# -gt 0 ]; then
  VARIANTS=("$1")
else
  VARIANTS=(onnx pytorch)
fi

for variant in "${VARIANTS[@]}"; do
  echo ">>> Ensure $variant has been idle ~15 min so it is cold. Ctrl-C to abort."
  sleep 5
  VARIANT="$variant" \
  PEAK_USERS=20 \
  SPAWN_RATE=1 \
  RAMP_SECONDS=60 \
  HOLD_SECONDS=300 \
  RPS_PER_USER=1.0 \
    "$RUNNER" shaped "ramp_${variant}_0to20"
done

echo "Test 9 complete."
