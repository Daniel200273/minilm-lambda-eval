#!/usr/bin/env bash
# Report Test 2 - Burst traffic. Fills Table 4.
#
# N in {1,5,10,15,25,50} simultaneous requests, 5 repetitions each,
# for both variants. 2 x 6 x 5 = 60 short runs, ~20-25 min total.
#
# With ReservedConcurrentExecutions = 10, expect zero failures for N <= 10
# and rising throttle-driven failures above it.
#
# Usage:
#   export HOST=...
#   ./experiments/test02_burst.sh            # both variants
#   ./experiments/test02_burst.sh onnx       # one variant only

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNNER="$SCRIPT_DIR/../run_experiment.sh"

if [ $# -gt 0 ]; then
  VARIANTS=("$1")
else
  VARIANTS=(onnx pytorch)
fi

NS=(1 5 10 15 25 50)
REPS=5

for variant in "${VARIANTS[@]}"; do
  for n in "${NS[@]}"; do
    for rep in $(seq 1 $REPS); do
      VARIANT="$variant" "$RUNNER" burst \
        "burst_${variant}_n${n}_run${rep}" \
        -u "$n" -r "$n" -t 30s
      sleep 5   # let throttle counters settle between runs
    done
  done
done

echo "Test 2 complete."
