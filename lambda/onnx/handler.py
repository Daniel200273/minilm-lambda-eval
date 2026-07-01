import json
import logging
import os
import sys
import time

import numpy as np
import onnxruntime as ort
from transformers import AutoTokenizer

ROOT = os.environ.get("LAMBDA_TASK_ROOT", os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "shared"))
from similarity import top_k_similar  # noqa: E402

MODEL_DIR = os.path.join(ROOT, "model", "onnx")
DATA_DIR = os.path.join(ROOT, "data")

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# --- Cold start: runs once per container ---
tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR)
session = ort.InferenceSession(os.path.join(MODEL_DIR, "model.onnx"), providers=["CPUExecutionProvider"])

with open(os.path.join(DATA_DIR, "corpus_questions.json")) as f:
    corpus_questions = json.load(f)
corpus_embeddings = np.load(os.path.join(DATA_DIR, "corpus_embeddings.npy"))


def _response(status_code, body):
    return {"statusCode": status_code, "body": json.dumps(body)}


def _encode(query):
    enc = tokenizer(query, max_length=128, padding=True, truncation=True, return_tensors="np")
    input_ids = enc["input_ids"].astype(np.int64)
    attention_mask = enc["attention_mask"].astype(np.int64)
    token_type_ids = np.zeros_like(input_ids)

    ort_inputs = {"input_ids": input_ids, "attention_mask": attention_mask}
    if "token_type_ids" in [i.name for i in session.get_inputs()]:
        ort_inputs["token_type_ids"] = token_type_ids

    token_embeddings = session.run(None, ort_inputs)[0]  # (1, seq_len, 384)

    mask = attention_mask[:, :, np.newaxis].astype(np.float32)
    pooled = (token_embeddings * mask).sum(axis=1) / mask.sum(axis=1).clip(min=1e-9)
    normalised = pooled / np.linalg.norm(pooled, axis=1, keepdims=True).clip(min=1e-9)

    return normalised[0], input_ids.shape[1]


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
        query_embedding, num_tokens = _encode(query)
        results = top_k_similar(query_embedding, corpus_embeddings, corpus_questions, k=top_k)
        inference_ms = (time.perf_counter() - start) * 1000
    except Exception:
        logger.exception("Unhandled error during inference")
        return _response(500, {"error": "Internal server error"})

    logger.info(json.dumps({
        "event": "inference",
        "query_tokens": num_tokens,
        "inference_ms": inference_ms,
        "variant": "onnx",
    }))

    return _response(200, {
        "query": query,
        "results": results,
        "inference_ms": inference_ms,
        "variant": "onnx",
    })
