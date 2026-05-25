@echo off
setlocal enabledelayedexpansion
title ContractLens — Setup

echo.
echo  ================================================
echo   ContractLens — First Time Setup
echo  ================================================
echo.

cd /d "%~dp0..\backend"

REM ── Check Python ─────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed.
    echo         Download it from: https://python.org
    pause & exit /b 1
)
echo [OK] Python found

REM ── Create .env if missing ───────────────────────
if not exist ".env" (
    echo.
    echo [SETUP] .env file not found — creating from template...
    copy .env.example .env >nul
    echo [OK] Created .env
    echo.
    echo =====================================================
    echo  IMPORTANT: Fill in your .env file before continuing
    echo =====================================================
    echo.
    echo  Open this file now:
    echo  %cd%\.env
    echo.
    echo  Required values:
    echo    OPENAI_API_KEY     = your OpenAI key (platform.openai.com)
    echo    SUPABASE_DB_URL    = from Supabase Dashboard > Settings > Database
    echo    SUPABASE_URL       = from Supabase Dashboard > Settings > API
    echo    SUPABASE_ANON_KEY  = from Supabase Dashboard > Settings > API
    echo.
    start notepad .env
    echo  Notepad is opening your .env file now.
    echo  Fill in your values, save the file, then come back here.
    echo.
    pause
)

REM ── Validate .env has real values ────────────────
findstr /C:"sk-your-openai" .env >nul 2>&1
if not errorlevel 1 (
    echo [ERROR] OPENAI_API_KEY is still the placeholder value.
    echo         Edit .env and add your real OpenAI key.
    start notepad .env
    pause & exit /b 1
)

findstr /C:"your-db-password" .env >nul 2>&1
if not errorlevel 1 (
    echo [ERROR] SUPABASE_DB_URL is still the placeholder value.
    echo         Edit .env and add your real Supabase connection string.
    start notepad .env
    pause & exit /b 1
)

echo [OK] .env file looks good

REM ── Install dependencies ─────────────────────────
echo.
echo [SETUP] Installing Python dependencies...
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo [ERROR] pip install failed. Try running as Administrator.
    pause & exit /b 1
)
echo [OK] Dependencies installed

REM ── Create uploads folder ─────────────────────────
if not exist "uploads" mkdir uploads
echo [OK] Uploads folder ready

REM ── Done ─────────────────────────────────────────
echo.
echo  ================================================
echo   Setup complete!
echo  ================================================
echo.
echo  Starting ContractLens...
echo  Your browser will open at: http://localhost:8000
echo.
echo  Press Ctrl+C to stop the server.
echo.

timeout /t 2 >nul
start "" "http://localhost:8000"
uvicorn main:app --reload --port 8000 --host 127.0.0.1
