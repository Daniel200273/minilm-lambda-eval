import numpy as np


def top_k_similar(query_embedding, corpus_embeddings, corpus_questions, k=5):
    """Return the top-k most similar corpus questions to query_embedding.

    Both query_embedding and corpus_embeddings are expected to be L2-normalised,
    so a plain dot product is equivalent to cosine similarity.

    query_embedding: np.ndarray, shape (384,)
    corpus_embeddings: np.ndarray, shape (N, 384), dtype float32
    corpus_questions: list[str], length N
    """
    scores = corpus_embeddings @ query_embedding
    top_idx = np.argsort(scores)[::-1][:k]

    return [
        {"rank": rank, "question": corpus_questions[idx], "score": float(scores[idx])}
        for rank, idx in enumerate(top_idx, start=1)
    ]
