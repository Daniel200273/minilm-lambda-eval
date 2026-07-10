#!/usr/bin/env bash
# Orchestrates everything that runs on the LAPTOP:
#   1. Test 1 - cold start (forced), both variants
#   2. Pulls whatever data EC2 has pushed so far
#   3. Collects CloudWatch data for every experiment run to date
#
# Does NOT include Test 7 (vertical scaling) - that one needs you to manually
# alternate `sam deploy` here with `test07_vertical_scaling.sh` on EC2 at each
# memory tier. Follow RUNNING_EXPERIMENTS.md for that one specifically.
#
# Requires: ~/minilm-env.sh already sourced, Learner Lab session active.
#
# Usage:  ./run_all_laptop_tests.sh

set -uo pipefail   # deliberately NOT -e: one failed step should not abort the rest

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || { echo "ERROR: cannot cd to $SCRIPT_DIR" >&2; exit 1; }

if [ -z "${ONNX_FN:-}" ] || [ -z "${PT_FN:-}" ]; then
  echo "ERROR: environment not loaded. Run:  source ~/minilm-env.sh" >&2
  exit 1
fi

FAILED=()
log() { echo ""; echo "=================================================="; echo "$1"; echo "=================================================="; }

STARTED=$(date -u +%Y-%m-%dT%H:%M:%SZ)

log "Test 1a - Cold start (onnx)"
./load_testing/cold_start_test.sh onnx 10 || FAILED+=("cold_start_onnx")

log "Test 1b - Cold start (pytorch)"
./load_testing/cold_start_test.sh pytorch 10 || FAILED+=("cold_start_pytorch")

log "Pulling any data pushed from EC2"
git pull origin main || FAILED+=("git_pull")

log "Collecting CloudWatch data for every experiment run so far"
python3 analysis/collect_all.py || FAILED+=("collect_all")

ENDED=$(date -u +%Y-%m-%dT%H:%M:%SZ)

log "DONE  (started $STARTED, ended $ENDED)"
if [ ${#FAILED[@]} -eq 0 ]; then
  echo "All steps completed."
else
  echo "Completed with failures in: ${FAILED[*]}"
  echo "Re-run just those steps individually - see RUNNING_EXPERIMENTS.md."
fi

echo ""
echo "Reminder: Test 7 (vertical scaling) is NOT included here - run it"
echo "separately, alternating 'sam deploy' (here) with"
echo "'test07_vertical_scaling.sh' (on EC2) at each memory tier."
