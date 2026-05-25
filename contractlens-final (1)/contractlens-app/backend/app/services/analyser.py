"""
services/analyser.py — Orchestrates the full analysis pipeline.

Full flow:
  upload PDF
    → parse_pdf (extract text, segment clauses)
    → embed_batch (OpenAI embeddings for all clauses)
    → store clauses + embeddings in DB
    → classify_clauses_batch (AI risk scoring for each clause)
    → store risk_results in DB
    → compute_document_risk_score
    → update document status = "done"
"""
import os
import uuid
import logging
from sqlalchemy.orm import Session

from app.services.pdf_parser import parse_pdf, ClauseChunk
from app.services.embedder import embed_batch
from app.services.classifier import classify_clauses_batch, compute_document_risk_score
from app.db.database import Document, Clause, RiskResult

logger = logging.getLogger(__name__)


async def run_analysis(document_id: str, pdf_path: str, db: Session) -> dict:
    """
    Full pipeline for one document. Called after upload.
    Updates the Document row in DB as it progresses.
    Returns summary dict on success.
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise ValueError(f"Document {document_id} not found in DB")

    try:
        # ── Step 1: PDF parsing ──────────────────────────────────────
        logger.info(f"[{document_id}] Step 1: Parsing PDF")
        clause_chunks, page_count = parse_pdf(pdf_path)

        doc.page_count   = page_count
        doc.clause_count = len(clause_chunks)
        db.commit()

        if not clause_chunks:
            raise ValueError("No clauses could be extracted from this PDF")

        # ── Step 2: Embed all clause texts ───────────────────────────
        logger.info(f"[{document_id}] Step 2: Embedding {len(clause_chunks)} clauses")
        texts = [chunk.text for chunk in clause_chunks]
        embeddings = embed_batch(texts)

        # ── Step 3: Store clauses + embeddings ───────────────────────
        logger.info(f"[{document_id}] Step 3: Storing clauses in DB")
        clause_rows = []
        for chunk, embedding in zip(clause_chunks, embeddings):
            clause_row = Clause(
                document_id    = document_id,
                clause_number  = chunk.clause_number,
                title          = chunk.title[:255] if chunk.title else "",
                text           = chunk.text,
                page           = chunk.page,
                embedding      = embedding
            )
            db.add(clause_row)
            clause_rows.append(clause_row)
        db.commit()

        # ── Step 4: AI risk classification ───────────────────────────
        logger.info(f"[{document_id}] Step 4: Classifying risks")
        clause_inputs = [
            {"text": chunk.text, "title": chunk.title}
            for chunk in clause_chunks
        ]
        risk_results = classify_clauses_batch(clause_inputs)

        # ── Step 5: Store risk results ───────────────────────────────
        logger.info(f"[{document_id}] Step 5: Storing risk results")
        flagged_count = 0
        for clause_row, risk in zip(clause_rows, risk_results):
            if risk["severity"] > 0:
                flagged_count += 1
                rr = RiskResult(
                    clause_id      = clause_row.id,
                    category       = risk["category_name"],
                    severity       = risk["severity"],
                    risk_level     = risk["risk_level"],
                    explanation    = risk["explanation"],
                    flagged_text   = risk["flagged_text"],
                    negotiate_tip  = risk["negotiate_tip"]
                )
                db.add(rr)
        db.commit()

        # ── Step 6: Compute overall risk score ───────────────────────
        risk_score = compute_document_risk_score(risk_results)
        doc.risk_score = risk_score
        doc.status     = "done"
        db.commit()

        # ── Clean up uploaded file ───────────────────────────────────
        try:
            os.remove(pdf_path)
            logger.info(f"[{document_id}] PDF deleted from disk")
        except Exception:
            pass  # Non-critical

        logger.info(f"[{document_id}] Analysis complete. Score: {risk_score}, Flagged: {flagged_count}")
        return {
            "document_id":  str(document_id),
            "status":       "done",
            "page_count":   page_count,
            "clause_count": len(clause_chunks),
            "flagged_count":flagged_count,
            "risk_score":   risk_score
        }

    except Exception as e:
        logger.error(f"[{document_id}] Analysis failed: {e}")
        doc.status = "error"
        db.commit()
        raise
