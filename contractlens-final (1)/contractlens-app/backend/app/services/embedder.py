"""
services/embedder.py — Convert clause text into vector embeddings.

Uses OpenAI text-embedding-3-small:
  - 1536 dimensions
  - ~$0.00002 per 1K tokens (very cheap)
  - Batched to minimise API calls

The embeddings are stored in pgvector and used for semantic
similarity search during retrieval.
"""
import openai
import numpy as np
from typing import Optional
from app.config import OPENAI_API_KEY, EMBEDDING_MODEL
import logging

logger = logging.getLogger(__name__)

# Initialise OpenAI client once
client = openai.OpenAI(api_key=OPENAI_API_KEY)

# Max chars per chunk before we truncate (model limit ~8192 tokens ≈ 32K chars)
MAX_CHARS = 8000


def _truncate(text: str) -> str:
    """Truncate text to model's token limit."""
    return text[:MAX_CHARS] if len(text) > MAX_CHARS else text


def embed_single(text: str) -> list[float]:
    """
    Embed a single text string. Returns a list of 1536 floats.
    Used for embedding user queries at retrieval time.
    """
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=_truncate(text)
    )
    return response.data[0].embedding


def embed_batch(texts: list[str], batch_size: int = 50) -> list[list[float]]:
    """
    Embed a list of texts efficiently by batching API calls.
    Returns list of embeddings in the same order as input texts.

    batch_size=50 is safe — OpenAI allows up to 2048 inputs per call,
    but batches of 50 keep latency manageable.
    """
    if not texts:
        return []

    all_embeddings: list[list[float]] = []
    truncated = [_truncate(t) for t in texts]

    for i in range(0, len(truncated), batch_size):
        batch = truncated[i:i + batch_size]
        try:
            response = client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=batch
            )
            # API returns embeddings in order
            batch_embeddings = [item.embedding for item in sorted(response.data, key=lambda x: x.index)]
            all_embeddings.extend(batch_embeddings)
            logger.info(f"Embedded batch {i // batch_size + 1}: {len(batch)} texts")
        except Exception as e:
            logger.error(f"Embedding batch failed at index {i}: {e}")
            # Fill with zeros so the pipeline doesn't crash
            all_embeddings.extend([[0.0] * 1536] * len(batch))

    return all_embeddings


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """
    Compute cosine similarity between two embedding vectors.
    Returns value between -1 and 1 (higher = more similar).
    """
    a = np.array(vec_a)
    b = np.array(vec_b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))
