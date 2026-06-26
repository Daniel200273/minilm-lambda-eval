"""
Step 2 — Pre-compute SQuAD question embeddings.
Run after export_to_onnx.py. Uses the ONNX model (no PyTorch needed).

Output (committed to repo, baked into both Docker images):
  lambda/shared/data/questions.json
  lambda/shared/data/embeddings.npy   (~1.5 MB for 1000 questions)
"""
import json
import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer
from datasets import load_dataset
from pathlib import Path

N = 1000
ONNX_DIR = Path("lambda/onnx")
OUT = Path("lambda/shared/data")
OUT.mkdir(parents=True, exist_ok=True)

tokenizer = Tokenizer.from_file(str(ONNX_DIR / "tokenizer.json"))
tokenizer.enable_padding(pad_id=0, pad_token="[PAD]")
tokenizer.enable_truncation(max_length=128)

session = ort.InferenceSession(
    str(ONNX_DIR / "model.onnx"), providers=["CPUExecutionProvider"]
)


def encode(texts: list[str], batch_size: int = 64) -> np.ndarray:
    batches = []
    for i in range(0, len(texts), batch_size):
        enc = tokenizer.encode_batch(texts[i : i + batch_size])
        input_ids      = np.array([e.ids            for e in enc], dtype=np.int64)
        attention_mask = np.array([e.attention_mask for e in enc], dtype=np.int64)
        token_type_ids = np.zeros_like(input_ids)

        last_hidden = session.run(None, {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
            "token_type_ids": token_type_ids,
        })[0]

        mask = attention_mask[:, :, np.newaxis].astype(np.float32)
        emb = (last_hidden * mask).sum(axis=1) / mask.sum(axis=1).clip(min=1e-9)
        emb /= np.linalg.norm(emb, axis=1, keepdims=True).clip(min=1e-9)
        batches.append(emb)

    return np.vstack(batches)


print(f"Loading {N} SQuAD questions...")
squad = load_dataset("rajpurkar/squad", split=f"train[:{N}]")
questions = list(squad["question"])

print("Encoding...")
embeddings = encode(questions)

(OUT / "questions.json").write_text(json.dumps(questions))
np.save(OUT / "embeddings.npy", embeddings)

print(f"Saved to {OUT}/")
print(f"  questions.json : {len(questions)} questions")
print(f"  embeddings.npy : {embeddings.shape}  "
      f"{embeddings.nbytes / 1e6:.1f} MB")
