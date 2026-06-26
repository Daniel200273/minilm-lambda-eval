import json
import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer
from pathlib import Path
from search import load_index, top_k

_DIR = Path(__file__).parent

# Cold-start: load once per container
_tokenizer = Tokenizer.from_file(str(_DIR / "tokenizer.json"))
_tokenizer.enable_padding(pad_id=0, pad_token="[PAD]")
_tokenizer.enable_truncation(max_length=128)

_session = ort.InferenceSession(
    str(_DIR / "model.onnx"), providers=["CPUExecutionProvider"]
)

_questions, _embeddings = load_index()


def _encode(text: str) -> np.ndarray:
    enc = _tokenizer.encode_batch([text])
    input_ids      = np.array([e.ids            for e in enc], dtype=np.int64)
    attention_mask = np.array([e.attention_mask for e in enc], dtype=np.int64)
    token_type_ids = np.zeros_like(input_ids)

    last_hidden = _session.run(None, {
        "input_ids":      input_ids,
        "attention_mask": attention_mask,
        "token_type_ids": token_type_ids,
    })[0]

    mask = attention_mask[:, :, np.newaxis].astype(np.float32)
    emb = (last_hidden * mask).sum(axis=1) / mask.sum(axis=1).clip(min=1e-9)
    emb /= np.linalg.norm(emb, axis=1, keepdims=True).clip(min=1e-9)
    return emb


def handler(event, context):
    try:
        body = json.loads(event.get("body") or "{}")
        query = str(body.get("query", "")).strip()
        k = int(body.get("top_k", 5))

        if not query:
            return {"statusCode": 400,
                    "body": json.dumps({"error": "query field required"})}

        q_emb = _encode(query)
        results = top_k(q_emb, _embeddings, _questions, k)

        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"query": query, "results": results}),
        }
    except Exception as exc:
        return {"statusCode": 500,
                "body": json.dumps({"error": str(exc)})}
