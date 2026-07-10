"""
Shared configuration for all locustfiles.

Environment variables (all optional):
  VARIANT          "onnx" (default) | "pytorch"   -> /onnx/search or /pytorch/search
  QUESTION_BUCKET  "all" (default) | "short" | "medium" | "long"
  TOP_K            integer (default 5)

data/user_questions.json is a flat list of dicts:
  {"id": 0, "question": "...", "bucket": "short", "n_tokens": 6}
"""
import json
import os
import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
QUESTIONS_PATH = REPO_ROOT / "data" / "user_questions.json"

VARIANT = os.environ.get("VARIANT", "onnx")
if VARIANT not in ("onnx", "pytorch"):
    raise ValueError(f"VARIANT must be 'onnx' or 'pytorch', got {VARIANT!r}")

ENDPOINT_PATH = f"/{VARIANT}/search"

BUCKET = os.environ.get("QUESTION_BUCKET", "all")
TOP_K = int(os.environ.get("TOP_K", "5"))

# Stats label. Keeping the bucket in the label means a run that mixes buckets
# would still be separable, and a single-bucket run is self-documenting in the
# Locust CSV output.
STATS_NAME = f"{ENDPOINT_PATH} [{BUCKET}]"


def load_questions():
    """Return the list of question dicts for the configured bucket."""
    with open(QUESTIONS_PATH) as f:
        data = json.load(f)

    if BUCKET == "all":
        pool = data
    else:
        pool = [q for q in data if q["bucket"] == BUCKET]

    if not pool:
        raise ValueError(
            f"No questions for bucket {BUCKET!r}. "
            f"Valid buckets: {sorted({q['bucket'] for q in data})}"
        )
    return pool
