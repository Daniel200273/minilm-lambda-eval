"""
Curate 100 user-facing benchmark queries from the SQuAD v2 VALIDATION split
(disjoint from the train-split corpus used in precompute_embeddings.py).

Questions are partitioned by whitespace-token count into three buckets:
  short:  <= 8 tokens
  medium: 9-19 tokens
  long:   >= 20 tokens

Saves data/user_questions.json as a list of
  {"id": int, "question": str, "bucket": str, "n_tokens": int}
"""
import json
import os

from datasets import load_dataset

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(REPO_ROOT, "data")

BUCKET_TARGETS = {"short": 34, "medium": 33, "long": 33}


def bucket_for(n_tokens):
    if n_tokens <= 8:
        return "short"
    if n_tokens <= 19:
        return "medium"
    return "long"


def main():
    os.makedirs(DATA_DIR, exist_ok=True)

    print("Loading SQuAD v2 validation split...")
    dataset = load_dataset("squad_v2", split="validation")

    buckets = {"short": [], "medium": [], "long": []}
    seen = set()

    for question in dataset["question"]:
        question = question.strip()
        if not question or question in seen:
            continue

        n_tokens = len(question.split())
        bucket = bucket_for(n_tokens)
        if len(buckets[bucket]) >= BUCKET_TARGETS[bucket]:
            continue

        seen.add(question)
        buckets[bucket].append({"question": question, "bucket": bucket, "n_tokens": n_tokens})

        if all(len(buckets[b]) >= BUCKET_TARGETS[b] for b in BUCKET_TARGETS):
            break

    curated = buckets["short"] + buckets["medium"] + buckets["long"]
    for i, entry in enumerate(curated):
        entry["id"] = i
    curated = [
        {"id": e["id"], "question": e["question"], "bucket": e["bucket"], "n_tokens": e["n_tokens"]}
        for e in curated
    ]

    output_path = os.path.join(DATA_DIR, "user_questions.json")
    with open(output_path, "w") as f:
        json.dump(curated, f, indent=2)

    print("\nDone.")
    print(f"  {output_path}  ({len(curated)} questions)")
    for bucket in BUCKET_TARGETS:
        count = sum(1 for e in curated if e["bucket"] == bucket)
        print(f"    {bucket}: {count}")


if __name__ == "__main__":
    main()
