"""
main.py — ContractLens FastAPI application.
Serves both API + frontend from one server.
Run: uvicorn main:app --reload --port 8000
"""
import logging, time
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from app.config import ALLOWED_ORIGINS, ENVIRONMENT, IS_PRODUCTION, validate_config
from app.db.database import create_tables
from app.routers.analysis import router as analysis_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"🚀 ContractLens [{ENVIRONMENT}] starting")
    if not validate_config():
        logger.error("❌ Missing env vars — check .env")
    try:
        create_tables()
    except Exception as e:
        logger.error(f"❌ DB init failed: {e} — check SUPABASE_DB_URL in .env")
    yield
    logger.info("ContractLens shutting down")

app = FastAPI(title="ContractLens API", version="1.0.0", docs_url="/api/docs", redoc_url="/api/redoc", lifespan=lifespan)

app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.middleware("http")
async def security_and_timing(request: Request, call_next):
    start = time.time()
    response: Response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Response-Time"] = f"{round((time.time()-start)*1000,1)}ms"
    return response

@app.exception_handler(Exception)
async def global_error(request: Request, exc: Exception):
    logger.error(f"Error on {request.url.path}: {exc}")
    return JSONResponse(status_code=500, content={"error": "Internal server error", "detail": str(exc) if not IS_PRODUCTION else "Something went wrong."})

app.include_router(analysis_router)

@app.get("/api/health", tags=["system"])
def health():
    return {"status": "ok", "service": "ContractLens", "version": "1.0.0", "environment": ENVIRONMENT, "database": "supabase"}

# Serve frontend static files
if FRONTEND_DIR.exists():
    app.mount("/css", StaticFiles(directory=str(FRONTEND_DIR / "css")), name="css")
    if (FRONTEND_DIR / "js").exists():
        app.mount("/js", StaticFiles(directory=str(FRONTEND_DIR / "js")), name="js")

    @app.get("/", include_in_schema=False)
    def index(): return FileResponse(str(FRONTEND_DIR / "index.html"))

    @app.get("/upload", include_in_schema=False)
    def upload_page(): return FileResponse(str(FRONTEND_DIR / "upload.html"))

    @app.get("/results", include_in_schema=False)
    def results_page(): return FileResponse(str(FRONTEND_DIR / "results.html"))

    @app.get("/{page}.html", include_in_schema=False)
    def html_page(page: str):
        p = FRONTEND_DIR / f"{page}.html"
        return FileResponse(str(p)) if p.exists() else FileResponse(str(FRONTEND_DIR / "index.html"))

    logger.info(f"✅ Frontend at {FRONTEND_DIR}")
