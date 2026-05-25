"""
models/schemas.py — Pydantic models for all API request/response bodies.

FastAPI uses these to:
  - Validate incoming request data
  - Serialise outgoing response data
  - Auto-generate OpenAPI documentation
"""
from pydantic import BaseModel, UUID4
from typing import Optional
from datetime import datetime


# ── Upload response ─────────────────────────────────────────────────────

class UploadResponse(BaseModel):
    document_id: str
    filename: str
    status: str           # "processing"
    message: str


# ── Risk result (one per flagged clause) ────────────────────────────────

class RiskResultSchema(BaseModel):
    id: str
    clause_id: str
    category: str
    severity: int         # 0–5
    risk_level: str       # low | medium | high
    explanation: str
    flagged_text: str
    negotiate_tip: str

    class Config:
        from_attributes = True


# ── Clause (with nested risk results) ───────────────────────────────────

class ClauseSchema(BaseModel):
    id: str
    clause_number: str
    title: str
    text: str
    page: int
    risk_results: list[RiskResultSchema] = []

    class Config:
        from_attributes = True


# ── Full document analysis response ─────────────────────────────────────

class AnalysisResponse(BaseModel):
    document_id: str
    filename: str
    status: str
    page_count: int
    clause_count: int
    risk_score: float       # 0–100
    risk_level: str         # low | medium | high
    high_risk_count: int
    medium_risk_count: int
    low_risk_count: int
    clauses: list[ClauseSchema]
    created_at: str

    class Config:
        from_attributes = True


# ── Document status check ────────────────────────────────────────────────

class StatusResponse(BaseModel):
    document_id: str
    status: str             # processing | done | error
    progress_message: str


# ── Ask a question about the contract ───────────────────────────────────

class QuestionRequest(BaseModel):
    question: str

class QuestionResponse(BaseModel):
    answer: str
    relevant_clauses: list[ClauseSchema]
