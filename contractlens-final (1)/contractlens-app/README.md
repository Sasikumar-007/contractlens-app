# ContractLens — Full Stack Application

AI-powered contract risk analyser. Upload any contract PDF and get
plain-English risk analysis in under 60 seconds.

---

## Folder structure

```
contractlens-app/
├── frontend/                  ← HTML/CSS/JS (served by FastAPI)
│   ├── index.html             ← Landing page
│   ├── upload.html            ← Upload page
│   ├── results.html           ← Analysis results page
│   ├── css/
│   │   └── design.css         ← Full design system (from DESIGN.md)
│   └── js/
│       └── api.js             ← Centralised API service layer
│
├── backend/                   ← FastAPI Python server
│   ├── main.py                ← App entry point (serves frontend + API)
│   ├── requirements.txt
│   ├── .env.example           ← Copy this to .env
│   ├── uploads/               ← Temp PDF storage (auto-deleted after analysis)
│   └── app/
│       ├── config.py          ← All env vars in one place
│       ├── db/
│       │   └── database.py    ← SQLAlchemy + pgvector (Supabase)
│       ├── models/
│       │   └── schemas.py     ← Pydantic request/response models
│       ├── routers/
│       │   └── analysis.py    ← All API endpoints
│       └── services/
│           ├── pdf_parser.py  ← PDF extraction + clause segmentation
│           ├── embedder.py    ← OpenAI embeddings (batched)
│           ├── classifier.py  ← AI risk scoring (15 categories)
│           ├── retriever.py   ← Hybrid search (semantic + BM25)
│           └── analyser.py    ← Pipeline orchestrator
│
└── scripts/
    ├── start.bat              ← Windows one-click start
    └── start.sh               ← Mac/Linux one-click start
```

---

## Prerequisites

- Python 3.11 or newer → https://python.org
- OpenAI API key → https://platform.openai.com/api-keys
- Supabase project → https://supabase.com (free tier works)

---

## Step 1 — Supabase setup

1. Create a free project at supabase.com
2. Go to **SQL Editor** and run:
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```
3. Go to **Settings → Database → Connection string → URI tab**
4. Copy the URI — looks like:
   ```
   postgresql://postgres:[PASSWORD]@db.[REF].supabase.co:5432/postgres
   ```
5. Go to **Settings → API** and copy your **anon key** and **project URL**

---

## Step 2 — Configure environment

```bash
cd contractlens-app/backend
cp .env.example .env
```

Edit `.env` and fill in:
```
OPENAI_API_KEY=sk-your-key-here
SUPABASE_DB_URL=postgresql://postgres:YOUR-PASSWORD@db.YOUR-REF.supabase.co:5432/postgres
SUPABASE_URL=https://YOUR-REF.supabase.co
SUPABASE_ANON_KEY=your-anon-key
```

---

## Step 3 — Install dependencies

```bash
cd contractlens-app/backend
pip install -r requirements.txt
```

---

## Step 4 — Run the application

**Windows:**
```
Double-click scripts\start.bat
```

**Mac / Linux:**
```bash
bash scripts/start.sh
```

**Manual:**
```bash
cd contractlens-app/backend
uvicorn main:app --reload --port 8000
```

---

## Step 5 — Open the app

| URL | What it is |
|---|---|
| http://localhost:8000 | The full app (landing page) |
| http://localhost:8000/upload | Upload a contract |
| http://localhost:8000/results?id=... | Results page |
| http://localhost:8000/api/docs | Interactive API docs (Swagger) |
| http://localhost:8000/api/health | Health check |

> **Note:** You no longer need a separate frontend server.
> FastAPI serves the HTML pages AND handles all API calls.

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| POST | /api/upload | Upload a contract PDF |
| GET | /api/status/{id} | Poll analysis status |
| GET | /api/results/{id} | Get full risk analysis |
| POST | /api/ask/{id} | Ask a question about the contract |
| DELETE | /api/document/{id} | Delete a document |
| GET | /api/health | Health check |

---

## Deployment

### Backend → Railway (recommended, free tier)

1. Push `contractlens-app/` to GitHub
2. Go to railway.app → New Project → Deploy from GitHub
3. Set root directory to `backend/`
4. Add environment variables (same as your .env)
5. Railway auto-detects FastAPI and deploys
6. Your app URL will be something like `https://contractlens.railway.app`

### Frontend

No separate deployment needed — FastAPI serves the frontend.
Your Railway URL is the full app.

### Custom domain (optional)

In Railway → Settings → Domains → Add custom domain.

---

## Supabase tables (auto-created on first run)

| Table | Description |
|---|---|
| documents | One row per uploaded contract |
| clauses | One row per extracted clause + pgvector embedding |
| risk_results | One row per risk finding per clause |

All tables are created automatically when the server starts.
You can view them in Supabase → Table Editor.

---

## Troubleshooting

**"SUPABASE_DB_URL is not set"**
→ Check your .env file — make sure you copied .env.example and filled it in

**"SSL connection error"**
→ Make sure your SUPABASE_DB_URL doesn't have `sslmode=disable`

**"No clauses extracted"**
→ The PDF is likely a scanned image. Try a text-based PDF.

**OpenAI errors**
→ Check your OPENAI_API_KEY and ensure you have billing credits

**Results page shows mock data**
→ Normal if no `?id=` is in the URL. Upload a real contract first.
