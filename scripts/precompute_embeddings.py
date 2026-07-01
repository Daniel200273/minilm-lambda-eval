"""
Precompute the corpus of SQuAD questions and their MiniLM embeddings.

Loads the SQuAD v2 TRAIN split, collects the first 2000 unique non-empty
questions, embeds them with sentence-transformers, and saves:
  - data/corpus_questions.json  (list[str], length 2000)
  - data/corpus_embeddings.npy  (float32, shape (2000, 384), L2-normalised)
"""
import json
import os

import numpy as np
from datasets import load_dataset
from sentence_transformers import SentenceTransformer

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(REPO_ROOT, "data")
CORPUS_SIZE = 2000


def main():
    os.makedirs(DATA_DIR, exist_ok=True)

    print("Loading SQuAD v2 train split...")
    dataset = load_dataset("squad_v2", split="train")

    questions = []
    seen = set()
    for question in dataset["question"]:
        question = question.strip()
        if not question or question in seen:
            continue
        seen.add(question)
        questions.append(question)
        if len(questions) == CORPUS_SIZE:
            break

    print(f"Collected {len(questions)} unique questions")

    print("Loading sentence-transformers/all-MiniLM-L6-v2...")
    model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

    print("Embedding corpus...")
    embeddings = model.encode(
        questions,
        normalize_embeddings=True,
        batch_size=256,
        show_progress_bar=True,
        convert_to_numpy=True,
    ).astype(np.float32)

    questions_path = os.path.join(DATA_DIR, "corpus_questions.json")
    embeddings_path = os.path.join(DATA_DIR, "corpus_embeddings.npy")

    with open(questions_path, "w") as f:
        json.dump(questions, f)
    np.save(embeddings_path, embeddings)

    print("\nDone.")
    print(f"  {questions_path}  ({len(questions)} questions)")
    print(f"  {embeddings_path}  (shape {embeddings.shape}, dtype {embeddings.dtype})")


if __name__ == "__main__":
    main()
