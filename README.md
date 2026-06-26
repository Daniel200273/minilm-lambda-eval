# MiniLM Lambda Eval

Semantic search over SQuAD questions using MiniLM-L6 exported to ONNX.
Designed to run on AWS with minimal dependencies (no PyTorch at inference time).

---

## Setup

```bash
uv venv .venv --seed
uv pip install sentence-transformers optimum[onnxruntime] datasets huggingface_hub onnxruntime tokenizers numpy
```

---

## Step 1 — Download the model

The model (`all-MiniLM-L6-v2`) is already included in `minilm-model/`.
If you need to re-download it, run:

```python
from sentence_transformers import SentenceTransformer
SentenceTransformer("all-MiniLM-L6-v2").save("./minilm-model")
```

---

## Step 2 — Export to ONNX

Run once to convert the PyTorch model to ONNX format (requires PyTorch and `optimum`):

```bash
python export_onnx.py
```

This produces `minilm-onnx/model.onnx` and `minilm-onnx/tokenizer.json`.
These two files are the only ones needed at inference time.

---

## Step 3 — Run semantic search

```bash
python main.py
```

Optional arguments:

| Flag | Default | Description |
|------|---------|-------------|
| `--n` | 100000 | Number of SQuAD questions to index |
| `--top` | 5 | Top results shown per query |

Example:

```bash
python main.py --n 5000 --top 10
```

Queries are loaded from `queries.json` (100 pre-defined questions).
Results show the most semantically similar SQuAD questions for each query.
