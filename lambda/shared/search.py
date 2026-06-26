import json
import numpy as np
from pathlib import Path

_DATA = Path(__file__).parent / "data"


def load_index() -> tuple[list[str], np.ndarray]:
    questions = json.loads((_DATA / "questions.json").read_text())
    embeddings = np.load(_DATA / "embeddings.npy")
    return questions, embeddings


def top_k(q_emb: np.ndarray, embeddings: np.ndarray,
          questions: list[str], k: int = 5) -> list[dict]:
    scores = (embeddings @ q_emb.T).squeeze()
    idx = np.argsort(scores)[::-1][:k]
    return [
        {"rank": i + 1, "score": float(scores[j]), "question": questions[j]}
        for i, j in enumerate(idx)
    ]
