import json
import logging
import os
import sys
import time

import numpy as np
from sentence_transformers import SentenceTransformer

ROOT = os.environ.get("LAMBDA_TASK_ROOT", os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "shared"))
from similarity import top_k_similar  # noqa: E402

MODEL_DIR = os.path.join(ROOT, "model", "pytorch")
DATA_DIR = os.path.join(ROOT, "data")

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# --- Cold start: runs once per container ---
model = SentenceTransformer(MODEL_DIR)

with open(os.path.join(DATA_DIR, "corpus_questions.json")) as f:
    corpus_questions = json.load(f)
corpus_embeddings = np.load(os.path.join(DATA_DIR, "corpus_embeddings.npy"))


def _response(status_code, body):
    return {"statusCode": status_code, "body": json.dumps(body)}


def lambda_handler(event, context=None):
    try:
        if isinstance(event, dict) and "body" in event and event["body"] is not None:
            raw_body = event["body"]
            payload = json.loads(raw_body) if isinstance(raw_body, str) else raw_body
        else:
            payload = event if isinstance(event, dict) else {}
    except json.JSONDecodeError:
        return _response(400, {"error": "Invalid JSON in request body"})

    query = payload.get("query") if isinstance(payload, dict) else None
    if not query:
        return _response(400, {"error": "Missing required field: query"})

    top_k = payload.get("top_k", 5)

    try:
        start = time.perf_counter()
        query_embedding = model.encode(query, normalize_embeddings=True, convert_to_numpy=True)
        results = top_k_similar(query_embedding, corpus_embeddings, corpus_questions, k=top_k)
        inference_ms = (time.perf_counter() - start) * 1000
        num_tokens = len(model.tokenizer.tokenize(query))
    except Exception:
        logger.exception("Unhandled error during inference")
        return _response(500, {"error": "Internal server error"})

    logger.info(json.dumps({
        "event": "inference",
        "query_tokens": num_tokens,
        "inference_ms": inference_ms,
        "variant": "pytorch",
    }))

    return _response(200, {
        "query": query,
        "results": results,
        "inference_ms": inference_ms,
        "variant": "pytorch",
    })
