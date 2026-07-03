# Setup & Deploy Guide

## Prerequisites

Set up a Python 3.11 environment (matches the Lambda runtime) using whichever
tool you prefer — `venv`, `uv`, miniconda/`conda`, etc. — then install the
export-only deps declared in [`pyproject.toml`](../pyproject.toml)
(sentence-transformers, torch, optimum, onnxruntime, ...):

```bash
pip install -e ".[dev]"
pip install awscli aws-sam-cli
```

Docker must be installed and running locally (SAM builds container images).

## Step 1 — Export the model (local only, not committed)

```bash
python scripts/export_to_onnx.py
```

Downloads `sentence-transformers/all-MiniLM-L6-v2` from Hugging Face and writes:

- `model/onnx/` — ONNX graph + full HF tokenizer files (~88 MB)
- `model/pytorch/` — full sentence-transformers model (~91 MB)

**Both folders are gitignored — never commit them.** Every teammate (or fresh
clone) must re-run this script once before building. The Dockerfiles `COPY`
these folders directly into the container image at build time.

## Step 2 — Data (already committed, nothing to do)

`data/corpus_questions.json`, `data/corpus_embeddings.npy`, and
`data/user_questions.json` are already in the repo. Only re-run
`scripts/precompute_embeddings.py` / `scripts/curate_user_questions.py` if you
want to regenerate them with different parameters.

## Step 3 — Test handlers locally (no AWS needed)

```bash
python scripts/test_handlers_locally.py
```

Confirms both ONNX and PyTorch handlers return matching top-5 results.

## Step 4 — Build and test a Docker image locally (optional)

```bash
docker build -f lambda/onnx/Dockerfile -t minilm-onnx .
docker run -p 9000:8080 minilm-onnx

curl -X POST http://localhost:9000/2015-03-31/functions/function/invocations \
  -H "Content-Type: application/json" \
  -d '{"body": "{\"query\": \"Who invented the telephone?\", \"top_k\": 5}"}'
```

Swap `onnx` for `pytorch` to test the other variant. Build context must be the
repo root (the `.` at the end) — both Dockerfiles reference `data/` and
`model/` relative to root, not relative to `lambda/onnx/`.

## Step 5 — Deploy with SAM

```bash
sam build
sam deploy --guided   # first time: sets region, stack name, ECR repo
# sam build && sam deploy   for subsequent deploys
```

SAM deploys **both** functions from one template. At the end you'll see:

```
Outputs:
  OnnxEndpoint    = https://<api-id>.execute-api.<region>.amazonaws.com/onnx/search
  PytorchEndpoint = https://<api-id>.execute-api.<region>.amazonaws.com/pytorch/search
```

## Step 6 — Verify both endpoints

```bash
curl -s -X POST "$ONNX_ENDPOINT" \
  -H "Content-Type: application/json" \
  -d '{"query": "Who invented the telephone?", "top_k": 5}' | python -m json.tool

curl -s -X POST "$PYTORCH_ENDPOINT" \
  -H "Content-Type: application/json" \
  -d '{"query": "Who invented the telephone?", "top_k": 5}' | python -m json.tool
```

## Tuning memory

Both functions share the `MemorySize` parameter (default 1024 MB):

```bash
sam deploy --parameter-overrides MemorySize=2048
```

## Gotchas

- **LabRole**: SAM uses `arn:aws:iam::<account-id>:role/LabRole` — do not
  change the role name, AWS Academy Learner Lab doesn't allow creating new
  IAM roles.
- **Run Step 1 before `sam build`** — the build will fail with a
  missing-file error if `model/onnx/` and `model/pytorch/` don't exist yet.
- **Docker must be running** for `sam build`.
- **AWS Academy sessions expire** after ~4 hours — if credentials go stale
  mid-deploy, restart the Learner Lab and refresh `~/.aws/credentials`
  before retrying.