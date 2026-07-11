#!/usr/bin/env bash
# Verifies the deployed stack is ACTUALLY in the state you think it's in,
# before you spend hours running tests against it.
#
# Catches two failure modes that can silently corrupt data:
#   1. `sam deploy` no-op'd ("no changes to deploy") when you expected a
#      real change - e.g. memory tier is not what you asked for.
#   2. The endpoint is unreachable or erroring, producing empty/garbage
#      Locust CSVs that still "complete" without obviously failing.
#
# Run on the LAPTOP (needs AWS credentials). Takes ~10 seconds.
#
# Usage:
#   ./preflight_check.sh          # expects both functions at 3008 MiB (report default)
#   ./preflight_check.sh 1024     # expects both at 1024 MiB (a Test 7 tier)

set -uo pipefail

EXPECTED_MEM="${1:-3008}"
REGION=us-east-1
PASS=1

if [ -z "${ONNX_FN:-}" ] || [ -z "${PT_FN:-}" ]; then
  echo "FAIL: environment not loaded. Run: source ~/minilm-env.sh"
  exit 1
fi

echo "=== Checking deployed memory (expecting ${EXPECTED_MEM} MiB on both) ==="
for pair in "ONNX:$ONNX_FN" "PYTORCH:$PT_FN"; do
  name="${pair%%:*}"
  fn="${pair#*:}"
  actual=$(aws lambda get-function-configuration --function-name "$fn" \
    --region "$REGION" --query MemorySize --output text 2>&1)
  if [ "$actual" = "$EXPECTED_MEM" ]; then
    echo "  PASS  $name memory = ${actual} MiB"
  else
    echo "  FAIL  $name memory = ${actual} MiB (expected ${EXPECTED_MEM})"
    PASS=0
  fi
done

echo ""
echo "=== Deployed image tags (eyeball these look right) ==="
for pair in "ONNX:$ONNX_FN" "PYTORCH:$PT_FN"; do
  name="${pair%%:*}"
  fn="${pair#*:}"
  uri=$(aws lambda get-function --function-name "$fn" --region "$REGION" \
    --query "Code.ImageUri" --output text 2>&1)
  echo "  $name = $uri"
done

echo ""
echo "=== Smoke-testing both endpoints through API Gateway ==="
HOST_URL=$(aws cloudformation describe-stacks --stack-name minilm-lambda-eval --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='OnnxEndpoint'].OutputValue" --output text 2>&1 | sed 's|/onnx/search||')

if [ -z "$HOST_URL" ] || [[ "$HOST_URL" == *"error"* ]]; then
  echo "  FAIL  could not resolve stack outputs: $HOST_URL"
  PASS=0
else
  for path in onnx pytorch; do
    resp=$(curl -s -m 40 -X POST "$HOST_URL/$path/search" -H 'Content-Type: application/json' \
      -d '{"query":"preflight check","top_k":1}')
    echo "  --- /$path/search response ---"
    echo "$resp" | python3 -m json.tool 2>/dev/null || echo "$resp"
    if echo "$resp" | python3 -c "import sys,json; d=json.load(sys.stdin); exit(0 if 'results' in d else 1)" 2>/dev/null; then
      echo "  PASS  /$path/search returned real results"
    else
      echo "  FAIL  /$path/search -> $resp"
      PASS=0
    fi
  done
fi

echo ""
if [ "$PASS" = "1" ]; then
  echo "=== ALL CHECKS PASSED - safe to run tests at ${EXPECTED_MEM} MiB ==="
  exit 0
else
  echo "=== SOME CHECKS FAILED - fix these before running/re-running tests ==="
  exit 1
fi
