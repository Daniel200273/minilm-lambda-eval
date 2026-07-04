# Setup & Deploy Guide

## Prerequisites

Set up a **Python 3.12** environment (matches the Lambda runtime — the base
images are `public.ecr.aws/lambda/python:3.12`) using whichever tool you prefer
— `venv`, `uv`, miniconda/`conda`, etc. — then install the export-only deps
declared in [`pyproject.toml`](../pyproject.toml) (sentence-transformers, torch,
optimum, onnxruntime, ...):

```bash
uv sync --extra dev        # or: pip install -e ".[dev]"
pip install awscli aws-sam-cli
```

Docker must be installed and running locally (we build the container images by
hand — see Step 5).

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

Confirms both ONNX and PyTorch handlers return matching top-5 results. To test
the full containers with the Lambda Runtime Interface Emulator, see
[ldocker-test.md](ldocker-test.md).

## Step 4 — Build the images and push to ECR

We do **not** use `sam build`. On Windows, `sam build` silently produces no
image for `PackageType: Image` functions, so the template references each image
by an explicit `ImageUri` and we build/push with plain Docker.

The two ECR repos (`minilm-onnx`, `minilm-pytorch`) already exist. If deploying
into a fresh account, create them first:

```bash
aws ecr create-repository --repository-name minilm-onnx   --region us-east-1
aws ecr create-repository --repository-name minilm-pytorch --region us-east-1
```

Set your account/region, then build, log in, and push. **Tag with `:py312`**
(the tag the template expects); bump the tag whenever the image changes so
CloudFormation actually redeploys it:

```bash
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
REGION=us-east-1
ECR=$ACCOUNT.dkr.ecr.$REGION.amazonaws.com

# --platform linux/amd64 matches Architectures: [x86_64] in the template.
# --provenance=false keeps a single-arch manifest that Lambda accepts.
docker build --platform linux/amd64 --provenance=false \
  -f lambda/onnx/Dockerfile    -t $ECR/minilm-onnx:py312    .
docker build --platform linux/amd64 --provenance=false \
  -f lambda/pytorch/Dockerfile -t $ECR/minilm-pytorch:py312 .

aws ecr get-login-password --region $REGION \
  | docker login --username AWS --password-stdin $ECR

docker push $ECR/minilm-onnx:py312
docker push $ECR/minilm-pytorch:py312
```

Build context must be the repo root (the trailing `.`) — both Dockerfiles
reference `data/` and `model/` relative to root, not to `lambda/onnx/`.

## Step 5 — Deploy with SAM

Because the images are already in ECR and referenced by `ImageUri`, deploy is a
single step (no `sam build`):

```bash
sam deploy --resolve-image-repos \
  --parameter-overrides "OnnxMemorySize=3008 PytorchMemorySize=3008"
```

Memory defaults are already 3008 in the template, so plain `sam deploy` also
works. `samconfig.toml` holds the stack name / region. At the end you'll see:

```
Outputs:
  OnnxEndpoint    = https://<api-id>.execute-api.<region>.amazonaws.com/onnx/search
  PytorchEndpoint = https://<api-id>.execute-api.<region>.amazonaws.com/pytorch/search
```

> No `sam` installed? The template uses explicit `ImageUri` (nothing to
> package), so `aws cloudformation deploy --template-file template.yaml
> --stack-name minilm-lambda-eval --capabilities CAPABILITY_IAM
> --parameter-overrides OnnxMemorySize=3008 PytorchMemorySize=3008` works too.

## Step 6 — Verify both endpoints

The first request after a new image deploy cold-starts the function **and pulls
the image**, which can return HTTP 503 for the first ~10–20 s. Retry a few
times; it settles into 200s.

```bash
curl -s -X POST "$ONNX_ENDPOINT" \
  -H "Content-Type: application/json" \
  -d '{"query": "Who invented the telephone?", "top_k": 5}' | python -m json.tool

curl -s -X POST "$PYTORCH_ENDPOINT" \
  -H "Content-Type: application/json" \
  -d '{"query": "Who invented the telephone?", "top_k": 5}' | python -m json.tool
```

Both return matching top-k results (scores identical to ~6 decimals). Warm
inference is ~25 ms (ONNX) vs ~700 ms (PyTorch).

## Tuning memory

Memory is set **per function** via `OnnxMemorySize` and `PytorchMemorySize`
(both default 3008 MB):

```bash
sam deploy --parameter-overrides "OnnxMemorySize=2048 PytorchMemorySize=3008"
```

**Do not drop below 3008 without testing the cold start.** Lambda scales vCPU
with memory; at 1024 MB neither function initialises within the 30 s API
Gateway limit — ONNX has to stream onnxruntime's shared libraries out of the
image, and the torch container is ~2.9 GB. 3008 MB gives the vCPU headroom to
cold-start in time.

## Gotchas

- **LabRole**: the template uses `arn:aws:iam::<account-id>:role/LabRole` — do
  not change the role name; AWS Academy Learner Lab doesn't allow creating new
  IAM roles.
- **`sam build` is a trap on Windows** — it produces no image for
  `PackageType: Image` functions and deploy then fails. Build with `docker
  build` and reference images by `ImageUri` (Step 4). This is why the template
  has no `Metadata: DockerfileUri` blocks.
- **CPU-only torch**: the PyTorch Dockerfile installs torch from the CPU wheel
  index. The default CUDA build drags in ~2 GB of unused NVIDIA libraries that
  only make the cold-start image pull slower (Lambda has no GPU).
- **Bump the image tag on changes** — CloudFormation only redeploys a function
  if its `ImageUri` string changes. Overwriting the same tag in ECR won't
  trigger an update; push a new tag and update `template.yaml`.
- **Run Step 1 before building** — `docker build` fails with a missing-file
  error if `model/onnx/` and `model/pytorch/` don't exist yet.
- **AWS Academy sessions expire** after ~4 hours — if credentials go stale
  mid-deploy, restart the Learner Lab and refresh `~/.aws/credentials` before
  retrying (a stale session shows up as an `explicit deny ... voc-cancel-cred`
  error).
- **Docker disk usage**: repeated image builds pile up in Docker's disk store
  and can fill the drive (each image is 1.3–2.7 GB). Run `docker image prune -f`
  between builds, and `docker rmi <old-tag>` after pushing.
