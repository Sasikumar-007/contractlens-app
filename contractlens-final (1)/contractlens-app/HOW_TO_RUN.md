# How to Run ContractLens on Your Computer

## What you need before starting

- [ ] Python installed (python.org)
- [ ] Your OpenAI API key (platform.openai.com/api-keys)
- [ ] Your Supabase project details (supabase.com)

---

## Step 1 — Get your Supabase details

Open your Supabase project and collect these 3 things:

**A. Database URL**
```
Supabase Dashboard
  → Settings (gear icon)
  → Database
  → Connection string
  → Click "URI" tab
  → Copy the full string
```
Looks like: `postgresql://postgres:mypassword@db.abcdefgh.supabase.co:5432/postgres`

**B. Project URL**
```
Supabase Dashboard
  → Settings
  → API
  → Copy "Project URL"
```
Looks like: `https://abcdefgh.supabase.co`

**C. Anon Key**
```
Supabase Dashboard
  → Settings
  → API
  → Copy "anon / public" key
```
Looks like: `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...` (very long)

**D. Enable pgvector in Supabase** (one time only)
```
Supabase Dashboard
  → SQL Editor
  → Paste and run this:
```
```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

---

## Step 2 — Fill in your .env file

1. Open the `contractlens-app/backend/` folder
2. Find the file called `.env.example`
3. Make a copy of it and rename the copy to `.env`
4. Open `.env` in Notepad and fill in your values:

```
OPENAI_API_KEY    = sk-proj-your-actual-key
SUPABASE_DB_URL   = postgresql://postgres:YOUR-PASSWORD@db.YOUR-REF.supabase.co:5432/postgres
SUPABASE_URL      = https://YOUR-REF.supabase.co
SUPABASE_ANON_KEY = your-anon-key
```

Save the file.

---

## Step 3 — Run the app

**Windows — double-click this file:**
```
contractlens-app/scripts/setup.bat
```

It will:
- Check your .env is filled in correctly
- Install all Python packages automatically
- Start the server
- Open your browser automatically

---

## Step 4 — Use the app

Your browser opens at: **http://localhost:8000**

| Page | URL |
|---|---|
| Home | http://localhost:8000 |
| Upload a contract | http://localhost:8000/upload |
| API documentation | http://localhost:8000/api/docs |

---

## If something goes wrong

**"OPENAI_API_KEY is still the placeholder"**
→ Open `.env`, replace `sk-your-openai-key-here` with your real key

**"SUPABASE_DB_URL is still the placeholder"**
→ Open `.env`, replace with your real Supabase connection string

**"SSL error" or "connection refused"**
→ Your Supabase DB URL might have a typo — copy it again fresh from the dashboard

**"No module named fastapi"**
→ Run this in Command Prompt inside the `backend` folder:
```
pip install -r requirements.txt
```

**"Port 8000 already in use"**
→ Something else is using port 8000. Change `PORT=8000` to `PORT=8001` in `.env`
→ Then visit http://localhost:8001 instead

---

## Stop the server

Press `Ctrl + C` in the terminal window.
