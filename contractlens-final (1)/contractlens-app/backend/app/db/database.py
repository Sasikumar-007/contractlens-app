"""
db/database.py — SQLAlchemy engine + pgvector models, configured for Supabase.

Supabase-specific settings:
  - SSL required (enforced via connect_args)
  - Connection pool tuned for Supabase's limits (max 15 connections on free tier)
  - pool_pre_ping=True — drops stale connections automatically
  - pgvector extension enabled via raw SQL on first run

Tables:
  documents    — one row per uploaded contract
  clauses      — one row per extracted clause + its pgvector embedding
  risk_results — one row per risk finding per clause
"""
from sqlalchemy import create_engine, Column, String, Integer, Float, Text, DateTime, ForeignKey, text
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from sqlalchemy.dialects.postgresql import UUID
from pgvector.sqlalchemy import Vector
import uuid
from datetime import datetime

from app.config import DATABASE_URL, EMBEDDING_DIMS, IS_PRODUCTION

# ── Engine ───────────────────────────────────────────────────────────────
# Supabase requires SSL; connect_args enforces it at the driver level
_connect_args = {"sslmode": "require"} if IS_PRODUCTION or "supabase" in DATABASE_URL else {}

engine = create_engine(
    DATABASE_URL,
    connect_args=_connect_args,
    pool_pre_ping=True,          # verify connection is alive before using it
    pool_size=5,                 # keep 5 persistent connections
    max_overflow=10,             # allow 10 extra under burst load
    pool_recycle=300,            # recycle connections every 5 minutes
    echo=False                   # set True for SQL debug logging
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()


# ── SQLAlchemy Models ────────────────────────────────────────────────────

class Document(Base):
    __tablename__ = "documents"

    id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename     = Column(String(255), nullable=False)
    page_count   = Column(Integer, default=0)
    clause_count = Column(Integer, default=0)
    risk_score   = Column(Float, default=0.0)           # 0–100
    status       = Column(String(50), default="processing")  # processing | done | error
    created_at   = Column(DateTime, default=datetime.utcnow)

    clauses      = relationship("Clause", back_populates="document", cascade="all, delete-orphan")


class Clause(Base):
    __tablename__ = "clauses"

    id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id   = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    clause_number = Column(String(50), default="")
    title         = Column(String(255), default="")
    text          = Column(Text, nullable=False)
    page          = Column(Integer, default=1)
    embedding     = Column(Vector(EMBEDDING_DIMS))       # pgvector: 1536-dim float array

    document      = relationship("Document", back_populates="clauses")
    risk_results  = relationship("RiskResult", back_populates="clause", cascade="all, delete-orphan")


class RiskResult(Base):
    __tablename__ = "risk_results"

    id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clause_id     = Column(UUID(as_uuid=True), ForeignKey("clauses.id", ondelete="CASCADE"), nullable=False)
    category      = Column(String(100), default="")
    severity      = Column(Integer, default=0)           # 0–5
    risk_level    = Column(String(20), default="low")    # low | medium | high
    explanation   = Column(Text, default="")
    flagged_text  = Column(Text, default="")
    negotiate_tip = Column(Text, default="")

    clause        = relationship("Clause", back_populates="risk_results")


# ── Session dependency (FastAPI) ─────────────────────────────────────────

def get_db():
    """
    FastAPI dependency — yields a DB session per request, closes after.
    Usage: db: Session = Depends(get_db)
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Table initialisation ─────────────────────────────────────────────────

def create_tables():
    """
    Called once at app startup.
    1. Enables pgvector extension in Supabase (idempotent — safe to run repeatedly)
    2. Creates all tables if they don't exist yet
    """
    with engine.connect() as conn:
        # pgvector must be enabled before creating Vector columns
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()

    # Create all tables defined above
    Base.metadata.create_all(bind=engine)
    print("✅ Supabase tables ready (documents, clauses, risk_results)")
