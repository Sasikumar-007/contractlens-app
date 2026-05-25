"""
services/retriever.py — Hybrid retrieval: semantic search + BM25 keyword search.

Why hybrid?
  - Semantic search (pgvector) finds conceptually similar clauses
    even if exact keywords differ
  - BM25 catches exact legal terms like "indemnification" or
    "liquidated damages" that semantic search can miss
  - Combined = best of both worlds

Used when:
  - User asks a question about the contract ("does this have a non-compete?")
  - Finding the most relevant clauses to re-analyse
"""
from sqlalchemy.orm import Session
from sqlalchemy import text
from rank_bm25 import BM25Okapi
from app.db.database import Clause
from app.services.embedder import embed_single
import logging
import re

logger = logging.getLogger(__name__)


def semantic_search(
    db: Session,
    document_id: str,
    query: str,
    top_k: int = 5
) -> list[dict]:
    """
    Find the top_k most semantically similar clauses to a query
    using pgvector cosine distance.
    """
    query_embedding = embed_single(query)

    # pgvector operator: <=> = cosine distance (lower = more similar)
    sql = text("""
        SELECT id, clause_number, title, text, page,
               1 - (embedding <=> CAST(:embedding AS vector)) AS similarity
        FROM clauses
        WHERE document_id = :doc_id
          AND embedding IS NOT NULL
        ORDER BY embedding <=> CAST(:embedding AS vector)
        LIMIT :top_k
    """)

    rows = db.execute(sql, {
        "embedding": str(query_embedding),
        "doc_id": str(document_id),
        "top_k": top_k
    }).fetchall()

    return [
        {
            "id": str(row.id),
            "clause_number": row.clause_number,
            "title": row.title,
            "text": row.text,
            "page": row.page,
            "score": float(row.similarity)
        }
        for row in rows
    ]


def bm25_search(
    clauses: list[dict],
    query: str,
    top_k: int = 5
) -> list[dict]:
    """
    BM25 keyword search over a list of clause dicts.
    Returns top_k results sorted by BM25 score.
    """
    if not clauses:
        return []

    # Tokenise
    tokenized_corpus = [_tokenize(c["text"]) for c in clauses]
    tokenized_query  = _tokenize(query)

    bm25 = BM25Okapi(tokenized_corpus)
    scores = bm25.get_scores(tokenized_query)

    # Attach scores and sort
    scored = [(clauses[i], float(scores[i])) for i in range(len(clauses))]
    scored.sort(key=lambda x: x[1], reverse=True)

    return [
        {**clause, "bm25_score": score}
        for clause, score in scored[:top_k]
        if score > 0
    ]


def hybrid_search(
    db: Session,
    document_id: str,
    query: str,
    top_k: int = 5
) -> list[dict]:
    """
    Combine semantic + BM25 results using Reciprocal Rank Fusion (RRF).

    RRF formula: score(d) = Σ 1 / (k + rank(d))
    where k=60 (standard constant that prevents top results dominating).

    Returns top_k unique clauses sorted by combined RRF score.
    """
    # Get all clauses for BM25 (needs full corpus)
    all_clauses = db.query(Clause).filter(
        Clause.document_id == document_id
    ).all()
    clause_dicts = [
        {"id": str(c.id), "clause_number": c.clause_number,
         "title": c.title, "text": c.text, "page": c.page}
        for c in all_clauses
    ]

    # Run both searches
    semantic_results = semantic_search(db, document_id, query, top_k=top_k * 2)
    bm25_results     = bm25_search(clause_dicts, query, top_k=top_k * 2)

    # Build RRF scores
    rrf_scores: dict[str, float] = {}
    id_to_clause: dict[str, dict] = {}
    K = 60

    for rank, result in enumerate(semantic_results, start=1):
        cid = result["id"]
        rrf_scores[cid] = rrf_scores.get(cid, 0) + 1 / (K + rank)
        id_to_clause[cid] = result

    for rank, result in enumerate(bm25_results, start=1):
        cid = result["id"]
        rrf_scores[cid] = rrf_scores.get(cid, 0) + 1 / (K + rank)
        if cid not in id_to_clause:
            id_to_clause[cid] = result

    # Sort by RRF score and return top_k
    sorted_ids = sorted(rrf_scores, key=lambda x: rrf_scores[x], reverse=True)

    return [
        {**id_to_clause[cid], "rrf_score": rrf_scores[cid]}
        for cid in sorted_ids[:top_k]
    ]


def _tokenize(text: str) -> list[str]:
    """Simple tokeniser: lowercase, split on non-alphanumeric."""
    return re.findall(r'\b[a-z]{2,}\b', text.lower())
