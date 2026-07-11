#!/usr/bin/env bash
# Report Test 5 - Input size effect. Fills Table 7.
#
# Burst tests at N in {1,10,15} for each question-length bucket.
# 5 repetitions each. 3 buckets x 3 Ns x 5 reps = 45 short runs (~15 min).
#
# Question buckets come from data/user_questions.json (34 short / 33 medium
# / 33 long). Because MiniLM truncates at 128 tokens and all buckets sit well
# under that, expect only moderate variation - which is the point of the test.
#
# Usage:
#   export HOST=...
#   ./experiments/test05_input_size.sh           # onnx (matches Table 7)
#   ./experiments/test05_input_size.sh pytorch

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNNER="$SCRIPT_DIR/../run_experiment.sh"

VARIANT_ARG="${1:-onnx}"
BUCKETS=(short medium long)
NS=(1 10 15)
REPS=5

for bucket in "${BUCKETS[@]}"; do
  for n in "${NS[@]}"; do
    for rep in $(seq 1 $REPS); do
      VARIANT="$VARIANT_ARG" QUESTION_BUCKET="$bucket" \
        "$RUNNER" burst \
        "inputsize_${VARIANT_ARG}_${bucket}_n${n}_run${rep}" \
        -u "$n" -r "$n" -t 30s
      sleep 5
    done
  done
done

echo "Test 5 complete."
