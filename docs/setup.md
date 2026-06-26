# Setup & Deploy Guide

## Prerequisites

Install locally (one-time):

```bash
pip install awscli aws-sam-cli docker
pip install optimum[onnxruntime] transformers torch sentence-transformers  # export only
pip install onnxruntime tokenizers numpy datasets huggingface_hub          # runtime
```

## Step 1 — Export model to ONNX

Downloads MiniLM-L6-v2 from Hugging Face and exports to `lambda/onnx/`:

```bash
python scripts/export_to_onnx.py
```

Output: `lambda/onnx/model.onnx` (~88 MB) and `lambda/onnx/tokenizer.json`.
Commit both files — they are the only artifacts needed for the Docker build.

> **Note**: `model.onnx` is 88 MB. GitHub accepts files up to 100 MB.
> If you hit push limits, enable Git LFS: `git lfs track "*.onnx"`.

## Step 2 — Pre-compute question embeddings

Downloads 1 000 SQuAD questions and encodes them using the ONNX model:

```bash
python scripts/precompute_embeddings.py
```

Output: `lambda/shared/data/questions.json` and `lambda/shared/data/embeddings.npy`.
Commit both — they are baked into the Docker image at build time.

## Step 3 — Build and test the Docker image locally

```bash
docker build -f lambda/onnx/Dockerfile -t minilm-onnx .

# Run locally on port 9000
docker run -p 9000:8080 minilm-onnx

# Test in a second terminal
curl -X POST http://localhost:9000/2015-03-31/functions/function/invocations \
  -H "Content-Type: application/json" \
  -d '{"body": "{\"query\": \"Who invented the telephone?\", \"top_k\": 5}"}'
```

## Step 4 — Deploy with SAM

```bash
# First deploy (interactive — sets region, stack name, ECR repo)
sam build
sam deploy --guided

# Subsequent deploys
sam build && sam deploy
```

SAM will:
1. Create an ECR repository automatically
2. Push the Docker image
3. Deploy the Lambda + HTTP API endpoint

At the end of the deploy, the endpoint URL is printed:

```
Outputs:
  SearchEndpoint = https://<api-id>.execute-api.<region>.amazonaws.com/search
```

## Step 5 — Verify the endpoint

```bash
ENDPOINT="https://<api-id>.execute-api.<region>.amazonaws.com/search"

curl -s -X POST $ENDPOINT \
  -H "Content-Type: application/json" \
  -d '{"query": "Who invented the telephone?", "top_k": 5}' | python -m json.tool
```

Expected response:

```json
{
  "query": "Who invented the telephone?",
  "results": [
    {"rank": 1, "score": 0.87, "question": "..."},
    ...
  ]
}
```

## Tuning memory

Memory is set via the `MemorySize` SAM parameter (default 512 MB).
To override at deploy time:

```bash
sam deploy --parameter-overrides MemorySize=1024
```

Higher memory also increases CPU allocation, which speeds up cold start and inference.

## Gotchas

- **LabRole**: SAM uses `arn:aws:iam::<account-id>:role/LabRole`. Do not change the role name.
- **ECR must exist in the same region** as the Lambda. SAM creates it automatically on first deploy.
- **Cold start**: ~1–2 s (ONNX model load + embedding index load). Subsequent calls are <100 ms.
- **sam build requires Docker** to be running locally.
- **AWS Academy sessions expire**: if credentials expire mid-deploy, re-start the lab and re-run `aws configure` before retrying.
