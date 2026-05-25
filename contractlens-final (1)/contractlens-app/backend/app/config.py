"""
config.py — Central configuration loader.

Reads all environment variables from .env via python-dotenv.
Every other module imports from here — never from os.environ directly.
This ensures one place to change any config value.
"""
import os
from dotenv import load_dotenv

# Load .env file (ignored if already set in shell environment)
load_dotenv()

# ── OpenAI ──────────────────────────────────────────────────────────────
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

# ── Database (Supabase PostgreSQL) ───────────────────────────────────────
# Supabase requires SSL — we enforce it via ?sslmode=require
_raw_db_url = os.getenv("SUPABASE_DB_URL", "")

if _raw_db_url:
    # Append SSL mode if not already present
    if "sslmode" not in _raw_db_url:
        DATABASE_URL = _raw_db_url + "?sslmode=require"
    else:
        DATABASE_URL = _raw_db_url
else:
    # Fallback for local Docker dev (no SSL needed)
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        "postgresql://contractlens:contractlens123@localhost:5432/contractlens"
    )

# ── Supabase API credentials (for JS client / future auth) ───────────────
SUPABASE_URL: str             = os.getenv("SUPABASE_URL", "")
SUPABASE_ANON_KEY: str        = os.getenv("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_ROLE_KEY: str= os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

# ── App settings ─────────────────────────────────────────────────────────
MAX_FILE_SIZE_MB: int = int(os.getenv("MAX_FILE_SIZE_MB", "20"))
UPLOAD_DIR: str       = os.getenv("UPLOAD_DIR", "./uploads")
ENVIRONMENT: str      = os.getenv("ENVIRONMENT", "development")
PORT: int             = int(os.getenv("PORT", "8000"))

IS_PRODUCTION = ENVIRONMENT == "production"

# ── CORS ─────────────────────────────────────────────────────────────────
ALLOWED_ORIGINS: list[str] = [
    o.strip() for o in
    os.getenv(
        "ALLOWED_ORIGINS",
        # Default: frontend + backend both on port 8000 (unified server)
        "http://localhost:8000,http://127.0.0.1:8000"
    ).split(",")
    if o.strip()
]

# In production, also allow any https origin (Netlify, Vercel, etc.)
if IS_PRODUCTION:
    ALLOWED_ORIGINS = ["*"]

# ── AI Models ────────────────────────────────────────────────────────────
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMS  = 1536
CHAT_MODEL      = "gpt-4o-mini"   # swap to "gpt-4o" for higher accuracy

# ── Ensure upload directory exists ───────────────────────────────────────
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ── Startup validation ───────────────────────────────────────────────────
def validate_config():
    """Call at startup to catch missing critical env vars early."""
    errors = []
    if not OPENAI_API_KEY:
        errors.append("OPENAI_API_KEY is not set")
    if not DATABASE_URL:
        errors.append("SUPABASE_DB_URL is not set")
    if errors:
        for e in errors:
            print(f"❌ Config error: {e}")
        return False
    return True
