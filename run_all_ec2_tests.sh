#!/usr/bin/env bash
# Orchestrates everything that runs on EC2:
#   Test 9 first (needs the functions genuinely idle - only valid if this is
#   the first test run since they were last used), then 2, 3, 5, 6, 10.
#   Finishes by pushing data/raw/ to git so the laptop can pick it up.
#
# Does NOT include Test 1 (needs AWS credentials - laptop only) or Test 7
# (needs alternating with a laptop-side `sam deploy`).
#
# Requires: export HOST="https://...execute-api...amazonaws.com" already set.
#
# Usage:  ./run_all_ec2_tests.sh

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || { echo "ERROR: cannot cd to $SCRIPT_DIR" >&2; exit 1; }

if [ -z "${HOST:-}" ]; then
  echo "ERROR: \$HOST is not set." >&2
  echo "  export HOST=\"https://<api-id>.execute-api.us-east-1.amazonaws.com\"" >&2
  exit 1
fi
export PATH="$HOME/.local/bin:$PATH"

FAILED=()
log() { echo ""; echo "=================================================="; echo "$1"; echo "=================================================="; }

STARTED=$(date -u +%Y-%m-%dT%H:%M:%SZ)

echo "WARNING: Test 9 needs both functions genuinely idle since last use."
echo "Only trust its 'cold' story if this is the first test of the session."
echo "Continuing in 5s (Ctrl-C to abort and run selectively instead)..."
sleep 5

log "Test 9a - Cold-start ramp (onnx)"
./load_testing/experiments/test09_ramp.sh onnx || FAILED+=("ramp_onnx")

log "Test 9b - Cold-start ramp (pytorch)"
./load_testing/experiments/test09_ramp.sh pytorch || FAILED+=("ramp_pytorch")

log "Test 2 - Burst traffic (both variants)"
./load_testing/experiments/test02_burst.sh || FAILED+=("burst")

log "Test 3a - Steady traffic (onnx)"
./load_testing/experiments/test03_steady.sh onnx || FAILED+=("steady_onnx")

log "Test 3b - Steady traffic (pytorch)"
./load_testing/experiments/test03_steady.sh pytorch || FAILED+=("steady_pytorch")

log "Test 5 - Input size effect"
./load_testing/experiments/test05_input_size.sh || FAILED+=("input_size")

log "Test 6 - Framework comparison"
./load_testing/experiments/test06_framework.sh || FAILED+=("framework")

log "Test 10 - top-k sweep"
./load_testing/experiments/test10_topk.sh onnx || FAILED+=("topk")

log "Pushing collected data to git"
git add -f data/raw
if git diff --cached --quiet; then
  echo "(nothing new to commit)"
else
  git commit -m "EC2 experiment data: $(date -u +%Y-%m-%dT%H:%M:%SZ)" || FAILED+=("git_commit")
  git push origin main || FAILED+=("git_push")
fi

ENDED=$(date -u +%Y-%m-%dT%H:%M:%SZ)

log "DONE  (started $STARTED, ended $ENDED)"
if [ ${#FAILED[@]} -eq 0 ]; then
  echo "All steps completed and pushed."
else
  echo "Completed with failures in: ${FAILED[*]}"
  echo "Data from steps that DID succeed was still committed and pushed above."
fi

echo ""
echo "Next: on your LAPTOP, run ./run_all_laptop_tests.sh"
echo "(or at minimum: git pull && python3 analysis/collect_all.py)"
