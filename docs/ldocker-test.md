# Local Testing with Docker

Both Lambda variants can be built and tested entirely on your laptop using
the AWS Lambda Runtime Interface Emulator (RIE), which is built into the
`public.ecr.aws/lambda/python` base images. This lets you verify the full
pipeline — model load, tokenization, inference, response format — before
spending any AWS Learner Lab credit.

These commands are standard Docker CLI and work the same way regardless of
how Docker is running on your machine (Colima, Docker Desktop, OrbStack,
native Linux Docker, etc.).

## Prerequisites

- Docker installed and running
- `model/onnx/` and `model/pytorch/` generated locally (see
  [setup.md](setup.md) — run `python scripts/export_to_onnx.py` first)

## Build

```bash
docker build --platform linux/amd64 -f lambda/onnx/Dockerfile -t minilm-onnx .
docker build --platform linux/amd64 -f lambda/pytorch/Dockerfile -t minilm-pytorch .
```

`--platform linux/amd64` matches the architecture declared in
`template.yaml` and avoids wheel-availability issues that can occur when
building natively on Apple Silicon.

## Run

Use two separate terminals and leave both running.

**Terminal 1 — ONNX variant:**

```bash
docker run --platform linux/amd64 -p 9000:8080 minilm-onnx
```

**Terminal 2 — PyTorch variant:**

```bash
docker run --platform linux/amd64 -p 9001:8080 minilm-pytorch
```

## Test

Run these from a third terminal.

### Basic check, one query each

```bash
curl -X POST http://localhost:9000/2015-03-31/functions/function/invocations \
  -H "Content-Type: application/json" \
  -d '{"body": "{\"query\": \"Who invented the telephone?\", \"top_k\": 5}"}'

curl -X POST http://localhost:9001/2015-03-31/functions/function/invocations \
  -H "Content-Type: application/json" \
  -d '{"body": "{\"query\": \"Who invented the telephone?\", \"top_k\": 5}"}'
```

### Side-by-side comparison, pretty-printed

```bash
echo "=== ONNX ==="
curl -s -X POST http://localhost:9000/2015-03-31/functions/function/invocations \
  -H "Content-Type: application/json" \
  -d '{"body": "{\"query\": \"What causes rain?\", \"top_k\": 3}"}' | python3 -m json.tool

echo "=== PyTorch ==="
curl -s -X POST http://localhost:9001/2015-03-31/functions/function/invocations \
  -H "Content-Type: application/json" \
  -d '{"body": "{\"query\": \"What causes rain?\", \"top_k\": 3}"}' | python3 -m json.tool
```

Both should return matching top-k results — same questions, same ranking,
scores close to each other (not necessarily bit-identical between runtimes).

### Error handling check

```bash
curl -X POST http://localhost:9000/2015-03-31/functions/function/invocations \
  -H "Content-Type: application/json" \
  -d '{"body": "not valid json"}'

curl -X POST http://localhost:9001/2015-03-31/functions/function/invocations \
  -H "Content-Type: application/json" \
  -d '{"body": "not valid json"}'
```

Both should return a clean error response, not crash the container.

### Rough cold vs. warm timing

```bash
echo "ONNX cold:" && time curl -s -X POST http://localhost:9000/2015-03-31/functions/function/invocations \
  -H "Content-Type: application/json" -d '{"body": "{\"query\": \"test\", \"top_k\": 5}"}' > /dev/null

echo "ONNX warm:" && time curl -s -X POST http://localhost:9000/2015-03-31/functions/function/invocations \
  -H "Content-Type: application/json" -d '{"body": "{\"query\": \"test\", \"top_k\": 5}"}' > /dev/null

echo "PyTorch cold:" && time curl -s -X POST http://localhost:9001/2015-03-31/functions/function/invocations \
  -H "Content-Type: application/json" -d '{"body": "{\"query\": \"test\", \"top_k\": 5}"}' > /dev/null

echo "PyTorch warm:" && time curl -s -X POST http://localhost:9001/2015-03-31/functions/function/invocations \
  -H "Content-Type: application/json" -d '{"body": "{\"query\": \"test\", \"top_k\": 5}"}' > /dev/null
```

Not identical to a real Lambda cold start (no image pull, no AWS-specific
init), but a useful proxy before spending real credit on the formal
cold-start experiment.

## Stop

```bash
# Ctrl+C in both container terminals, then:
docker ps   # confirm nothing is still running
```

## Cleanup (optional)

```bash
docker rm -f $(docker ps -aq)
docker rmi -f $(docker images -aq)
```

Removes all local containers and images. Next build will start from
scratch (fresh base image pull, fresh pip install).