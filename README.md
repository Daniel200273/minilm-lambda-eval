# MiniLM Lambda Eval

Performance and scalability evaluation of AWS Lambda serving MiniLM-L6-v2 for
sentence similarity inference. Given a query question, the model retrieves the
top-5 most similar questions from a pre-indexed SQuAD corpus — simulating FAQ /
support-thread matching.

Two Lambda variants are deployed side by side for comparison:

- **ONNX** (`lambda/onnx/`) — onnxruntime + transformers tokenizer, no PyTorch at inference
- **PyTorch** (`lambda/pytorch/`) — sentence-transformers, standard inference path

---

## Repository structure

    data/               Pre-computed corpus embeddings + curated benchmark queries (committed)
    lambda/onnx/        ONNX variant: handler, Dockerfile, requirements
    lambda/pytorch/     PyTorch variant: handler, Dockerfile, requirements
    lambda/shared/      Shared cosine-similarity top-k lookup
    scripts/            One-time local scripts (model export, embedding precompute, tests)
    template.yaml       AWS SAM template — deploys both variants
    docs/setup.md       Full deployment walkthrough

## Quick start

Full instructions: [docs/setup.md](docs/setup.md). Short version:

```bash
pip install -r scripts/requirements-dev.txt
python scripts/export_to_onnx.py    # generates model/onnx/ and model/pytorch/ locally (gitignored)
sam build
sam deploy --guided
```

## Data

`data/corpus_questions.json` + `data/corpus_embeddings.npy` — ~2000 SQuAD
questions, pre-embedded with MiniLM. `data/user_questions.json` — 100
benchmark queries (disjoint from the corpus), bucketed by length
(short/medium/long) for the input-size load testing experiments.

Both are committed directly — see `scripts/precompute_embeddings.py` and
`scripts/curate_user_questions.py` if you need to regenerate them.