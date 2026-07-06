# Testing the Live AWS Endpoints

Once `sam deploy` has succeeded, use these commands to confirm both Lambda
variants are actually working on AWS (not just deployed).

## Prerequisites

- Valid AWS credentials (`aws sts get-caller-identity` should print your ARN,
  not an error). AWS Academy Learner Lab sessions expire after ~4 hours —
  refresh `~/.aws/credentials` if this fails.

```bash
aws sts get-caller-identity --query Arn --output text
```

## Step 1 — Get the endpoint URLs

Read them from the stack outputs rather than hardcoding — the API ID changes
if the stack is ever recreated.

```bash
aws cloudformation describe-stacks --stack-name minilm-lambda-eval \
  --region us-east-1 \
  --query "Stacks[0].Outputs" --output table
```

```powershell
aws cloudformation describe-stacks --stack-name minilm-lambda-eval `
  --region us-east-1 `
  --query "Stacks[0].Outputs" --output table
```

Save them for the commands below:

```bash
ONNX_ENDPOINT=$(aws cloudformation describe-stacks --stack-name minilm-lambda-eval \
  --region us-east-1 --query "Stacks[0].Outputs[?OutputKey=='OnnxEndpoint'].OutputValue" --output text)
PYTORCH_ENDPOINT=$(aws cloudformation describe-stacks --stack-name minilm-lambda-eval \
  --region us-east-1 --query "Stacks[0].Outputs[?OutputKey=='PytorchEndpoint'].OutputValue" --output text)
```

```powershell
$OnnxEndpoint = (aws cloudformation describe-stacks --stack-name minilm-lambda-eval `
  --region us-east-1 --query "Stacks[0].Outputs[?OutputKey=='OnnxEndpoint'].OutputValue" --output text)
$PytorchEndpoint = (aws cloudformation describe-stacks --stack-name minilm-lambda-eval `
  --region us-east-1 --query "Stacks[0].Outputs[?OutputKey=='PytorchEndpoint'].OutputValue" --output text)
```

## Step 2 — Basic check, one query each

```bash
curl -s -X POST "$ONNX_ENDPOINT" \
  -H "Content-Type: application/json" \
  -d '{"query": "Who invented the telephone?", "top_k": 5}' | python -m json.tool

curl -s -X POST "$PYTORCH_ENDPOINT" \
  -H "Content-Type: application/json" \
  -d '{"query": "Who invented the telephone?", "top_k": 5}' | python -m json.tool
```

```powershell
Invoke-RestMethod -Method Post -Uri $OnnxEndpoint -ContentType "application/json" `
  -Body '{"query": "Who invented the telephone?", "top_k": 5}'

Invoke-RestMethod -Method Post -Uri $PytorchEndpoint -ContentType "application/json" `
  -Body '{"query": "Who invented the telephone?", "top_k": 5}'
```

Expect a JSON body with `query`, `results` (ranked list with `question` +
`score`), `inference_ms`, and `variant` (`"onnx"` or `"pytorch"`).

## Step 3 — Cold start: retry on 503

**After a new image deploy, the first call pulls the image and can return
HTTP 503 for ~10–20 s.** This is expected, not a failure — retry a few times.

```bash
for i in 1 2 3 4 5; do
  code=$(curl -s -o /tmp/r.json -w "%{http_code}" -X POST "$ONNX_ENDPOINT" \
    -H "Content-Type: application/json" \
    -d '{"query": "test", "top_k": 3}' --max-time 35)
  echo "attempt $i: HTTP $code"
  [ "$code" = "200" ] && cat /tmp/r.json && break
  sleep 3
done
```

```powershell
for ($i = 1; $i -le 5; $i++) {
  try {
    $r = Invoke-RestMethod -Method Post -Uri $OnnxEndpoint -ContentType "application/json" `
      -Body '{"query": "test", "top_k": 3}' -TimeoutSec 35
    Write-Output "attempt ${i}: OK"; $r.results | Format-Table -AutoSize; break
  } catch {
    Write-Output "attempt ${i}: retrying..."
    Start-Sleep -Seconds 3
  }
}
```

(Note: `${i}:` needs the braces — PowerShell parses a bare `$i:` inside a
string as an invalid drive-qualified variable reference.)

## Step 4 — Side-by-side comparison (both variants should agree)

```bash
echo "=== ONNX ===" && curl -s -X POST "$ONNX_ENDPOINT" \
  -H "Content-Type: application/json" \
  -d '{"query": "What causes rain?", "top_k": 3}' | python -m json.tool

echo "=== PyTorch ===" && curl -s -X POST "$PYTORCH_ENDPOINT" \
  -H "Content-Type: application/json" \
  -d '{"query": "What causes rain?", "top_k": 3}' | python -m json.tool
```

Both should return the same ranked questions, with scores matching to ~5-6
decimal places (not necessarily bit-identical between runtimes). `inference_ms`
will differ a lot — ONNX is typically ~20-30 ms warm, PyTorch ~700-800 ms warm.

## Step 5 — Error handling check

```bash
curl -s -X POST "$ONNX_ENDPOINT" -H "Content-Type: application/json" -d 'not valid json'
curl -s -X POST "$PYTORCH_ENDPOINT" -H "Content-Type: application/json" -d 'not valid json'
```

Both should return a clean 4xx error body, not a 500 or a raw stack trace.

## Step 6 — Check which image is actually deployed

If results look off after a rebuild, confirm each function is running the
image you think it is:

```bash
aws lambda get-function --function-name <OnnxFunction-physical-id> \
  --query "Code.ImageUri" --output text --region us-east-1
```

```powershell
aws lambda get-function --function-name <OnnxFunction-physical-id> `
  --query "Code.ImageUri" --output text --region us-east-1
```

```powershell
aws lambda get-function --function-name minilm-lambda-eval-OnnxFunction-MkPzxF8uK8Ba `
  --query "Code.ImageUri" --output text --region us-east-1

aws lambda get-function --function-name minilm-lambda-eval-PytorchFunction-Qdklm2Yypeay `
  --query "Code.ImageUri" --output text --region us-east-1


```

(Find the physical function names with
`aws cloudformation describe-stack-resources --stack-name minilm-lambda-eval --region us-east-1`.)
