import json
import argparse
import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer
from datasets import load_dataset

parser = argparse.ArgumentParser()
parser.add_argument("--n", type=int, default=100000, help="Number of SQuAD questions to index")
parser.add_argument("--top", type=int, default=5, help="Top results to show per query")
args = parser.parse_args()

# Tokenizer from tokenizers library (Rust-based, no torch)
tokenizer = Tokenizer.from_file("./minilm-onnx/tokenizer.json")
tokenizer.enable_padding(pad_id=0, pad_token="[PAD]")   # dynamic padding per batch
tokenizer.enable_truncation(max_length=128)

# ONNX Runtime session (CPU only — no GPU needed for MiniLM)
session = ort.InferenceSession(
    "./minilm-onnx/model.onnx",
    providers=["CPUExecutionProvider"],
)
print("✅ ONNX model ready!")


def encode(texts: list[str] | str, batch_size: int = 64) -> np.ndarray:
    """Tokenize -> ONNX inference -> mean pool -> L2 normalize."""
    if isinstance(texts, str):
        texts = [texts]

    batches = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        enc = tokenizer.encode_batch(batch)

        input_ids      = np.array([e.ids            for e in enc], dtype=np.int64)
        attention_mask = np.array([e.attention_mask for e in enc], dtype=np.int64)
        token_type_ids = np.zeros_like(input_ids)

        # last_hidden_state: (batch, seq_len, 384)
        last_hidden = session.run(None, {
            "input_ids":      input_ids,
            "attention_mask": attention_mask,
            "token_type_ids": token_type_ids,
        })[0]

        # Mean pooling (mask out padding tokens)
        mask = attention_mask[:, :, np.newaxis].astype(np.float32)
        emb = (last_hidden * mask).sum(axis=1) / mask.sum(axis=1).clip(min=1e-9)

        # L2 normalize
        emb = emb / np.linalg.norm(emb, axis=1, keepdims=True).clip(min=1e-9)
        batches.append(emb)

    return np.vstack(batches)


# Load / cache dataset
print("⏳ Loading SQuAD dataset...")
squad = load_dataset("rajpurkar/squad", split=f"train[:{args.n}]")
squad.save_to_disk("squad-cache")
questions = list(squad["question"])
print(f"✅ Loaded {len(questions)} questions")

# Embed all dataset questions
print("⏳ Encoding dataset questions...")
embeddings = encode(questions)   # (n, 384), already L2-normalised
print(f"✅ Embeddings shape: {embeddings.shape}")

# Load queries
with open("queries.json") as f:
    queries = json.load(f)["queries"]

# Search
print(f"\n🔍 Running {len(queries)} queries (top {args.top} each)...")
for query in queries:
    q_emb = encode(query)                               # (1, 384)
    scores = (embeddings @ q_emb.T).squeeze()           # cosine sim (both normalised)
    top_idx = np.argsort(scores)[::-1][: args.top]

    print(f"\nQuery: '{query}'")
    for rank, idx in enumerate(top_idx, 1):
        print(f"   {rank}. ({scores[idx]:.2f}) {questions[idx]}")
