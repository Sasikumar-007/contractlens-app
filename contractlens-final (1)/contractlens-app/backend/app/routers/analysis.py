"""
routers/analysis.py — All API endpoints for ContractLens.

Endpoints:
  POST /api/upload          — Upload a PDF and start analysis
  GET  /api/status/{id}     — Poll analysis status (processing → done)
  GET  /api/results/{id}    — Get full analysis results
  POST /api/ask/{id}        — Ask a question about a specific contract
  DELETE /api/document/{id} — Delete a document and all its data
"""
import os
import uuid
import asyncio
import logging
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, BackgroundTasks
from sqlalchemy.orm import Session

from app.db.database import get_db, Document, Clause, RiskResult
from app.models.schemas import (
    UploadResponse, AnalysisResponse, StatusResponse,
    ClauseSchema, RiskResultSchema, QuestionRequest, QuestionResponse
)
from app.services.analyser import run_analysis
from app.services.retriever import hybrid_search
from app.config import MAX_FILE_SIZE_MB, UPLOAD_DIR, OPENAI_API_KEY, CHAT_MODEL
import openai

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["analysis"])

ALLOWED_TYPES = {"application/pdf", "application/msword",
                 "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}


# ── POST /api/upload ────────────────────────────────────────────────────

@router.post("/upload", response_model=UploadResponse)
async def upload_contract(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Upload a contract PDF. Returns a document_id immediately.
    Analysis runs in the background — poll /api/status/{id} to check progress.
    """
    # Validate file type
    if file.content_type not in ALLOWED_TYPES and not file.filename.endswith('.pdf'):
        raise HTTPException(400, "Only PDF, DOC, and DOCX files are supported")

    # Read and validate file size
    contents = await file.read()
    size_mb = len(contents) / (1024 * 1024)
    if size_mb > MAX_FILE_SIZE_MB:
        raise HTTPException(413, f"File too large. Maximum size is {MAX_FILE_SIZE_MB}MB")

    if len(contents) < 100:
        raise HTTPException(400, "File appears to be empty or corrupted")

    # Save to disk temporarily
    document_id = str(uuid.uuid4())
    safe_filename = f"{document_id}.pdf"
    pdf_path = os.path.join(UPLOAD_DIR, safe_filename)

    with open(pdf_path, "wb") as f:
        f.write(contents)

    # Create DB record
    doc = Document(
        id       = document_id,
        filename = file.filename or "contract.pdf",
        status   = "processing"
    )
    db.add(doc)
    db.commit()

    # Run analysis in background (non-blocking)
    background_tasks.add_task(_run_analysis_task, document_id, pdf_path)

    logger.info(f"Upload accepted: {file.filename} ({size_mb:.1f}MB) → {document_id}")

    return UploadResponse(
        document_id=document_id,
        filename=file.filename or "contract.pdf",
        status="processing",
        message="Analysis started. Poll /api/status/{document_id} for progress."
    )


async def _run_analysis_task(document_id: str, pdf_path: str):
    """Background task wrapper — creates its own DB session."""
    from app.db.database import SessionLocal
    db = SessionLocal()
    try:
        await run_analysis(document_id, pdf_path, db)
    except Exception as e:
        logger.error(f"Background analysis failed for {document_id}: {e}")
    finally:
        db.close()


# ── GET /api/status/{document_id} ───────────────────────────────────────

@router.get("/status/{document_id}", response_model=StatusResponse)
def get_status(document_id: str, db: Session = Depends(get_db)):
    """Poll this endpoint until status == 'done' or 'error'."""
    doc = _get_doc_or_404(document_id, db)

    messages = {
        "processing": "Analysing your contract — this takes about 30-60 seconds",
        "done":       "Analysis complete",
        "error":      "Analysis failed — please try uploading again"
    }

    return StatusResponse(
        document_id=document_id,
        status=doc.status,
        progress_message=messages.get(doc.status, "Unknown status")
    )


# ── GET /api/results/{document_id} ──────────────────────────────────────

@router.get("/results/{document_id}", response_model=AnalysisResponse)
def get_results(document_id: str, db: Session = Depends(get_db)):
    """Get the full analysis results for a completed document."""
    doc = _get_doc_or_404(document_id, db)

    if doc.status == "processing":
        raise HTTPException(202, "Analysis still in progress. Try again in a few seconds.")
    if doc.status == "error":
        raise HTTPException(500, "Analysis failed for this document.")

    # Load clauses with their risk results
    clauses = (
        db.query(Clause)
        .filter(Clause.document_id == document_id)
        .order_by(Clause.page)
        .all()
    )

    # Count risk levels
    high = medium = low = 0
    clause_schemas = []

    for clause in clauses:
        risk_schemas = []
        for rr in clause.risk_results:
            if rr.risk_level == "high":   high += 1
            elif rr.risk_level == "medium": medium += 1
            elif rr.risk_level == "low":    low += 1

            risk_schemas.append(RiskResultSchema(
                id=str(rr.id), clause_id=str(rr.clause_id),
                category=rr.category or "", severity=rr.severity,
                risk_level=rr.risk_level or "low",
                explanation=rr.explanation or "",
                flagged_text=rr.flagged_text or "",
                negotiate_tip=rr.negotiate_tip or ""
            ))

        clause_schemas.append(ClauseSchema(
            id=str(clause.id), clause_number=clause.clause_number or "",
            title=clause.title or "", text=clause.text, page=clause.page,
            risk_results=risk_schemas
        ))

    # Only include clauses that have at least one risk finding
    flagged_clauses = [c for c in clause_schemas if c.risk_results]

    risk_level = "low"
    if doc.risk_score >= 60: risk_level = "high"
    elif doc.risk_score >= 30: risk_level = "medium"

    return AnalysisResponse(
        document_id=document_id,
        filename=doc.filename,
        status=doc.status,
        page_count=doc.page_count or 0,
        clause_count=doc.clause_count or 0,
        risk_score=doc.risk_score or 0.0,
        risk_level=risk_level,
        high_risk_count=high,
        medium_risk_count=medium,
        low_risk_count=low,
        clauses=flagged_clauses,
        created_at=doc.created_at.isoformat() if doc.created_at else ""
    )


# ── POST /api/ask/{document_id} ─────────────────────────────────────────

@router.post("/ask/{document_id}", response_model=QuestionResponse)
def ask_question(
    document_id: str,
    body: QuestionRequest,
    db: Session = Depends(get_db)
):
    """
    Ask a natural language question about a specific contract.
    Uses hybrid retrieval to find relevant clauses, then GPT answers.
    Example: "Does this contract have a non-compete clause?"
    """
    doc = _get_doc_or_404(document_id, db)
    if doc.status != "done":
        raise HTTPException(400, "Document analysis is not complete yet")

    # Retrieve relevant clauses using hybrid search
    relevant = hybrid_search(db, document_id, body.question, top_k=4)

    if not relevant:
        return QuestionResponse(
            answer="I couldn't find relevant clauses to answer your question.",
            relevant_clauses=[]
        )

    # Build context from retrieved clauses
    context = "\n\n".join(
        f"[Clause {c['clause_number']} - {c['title']}]\n{c['text']}"
        for c in relevant
    )

    client = openai.OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a plain-English contract analyst helping a non-lawyer understand their contract. "
                    "Answer the question based ONLY on the contract clauses provided. "
                    "Be direct and clear. If the information is not in the provided clauses, say so. "
                    "Never make up or infer information not present in the text."
                )
            },
            {
                "role": "user",
                "content": f"CONTRACT CLAUSES:\n{context}\n\nQUESTION: {body.question}"
            }
        ],
        temperature=0.2,
        max_tokens=400
    )

    answer = response.choices[0].message.content

    # Map retrieved clauses to schema
    relevant_clause_ids = [c["id"] for c in relevant]
    clause_rows = db.query(Clause).filter(Clause.id.in_(relevant_clause_ids)).all()
    clause_schemas = [
        ClauseSchema(
            id=str(c.id), clause_number=c.clause_number or "",
            title=c.title or "", text=c.text, page=c.page,
            risk_results=[]
        )
        for c in clause_rows
    ]

    return QuestionResponse(answer=answer, relevant_clauses=clause_schemas)


# ── DELETE /api/document/{document_id} ──────────────────────────────────

@router.delete("/document/{document_id}")
def delete_document(document_id: str, db: Session = Depends(get_db)):
    """Delete a document and all associated clauses and risk results."""
    doc = _get_doc_or_404(document_id, db)
    db.delete(doc)
    db.commit()
    return {"message": "Document deleted successfully"}


# ── GET /api/health ──────────────────────────────────────────────────────

@router.get("/health")
def health():
    return {"status": "ok", "service": "ContractLens API"}


# ── Helper ───────────────────────────────────────────────────────────────

def _get_doc_or_404(document_id: str, db: Session) -> Document:
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(404, f"Document {document_id} not found")
    return doc
