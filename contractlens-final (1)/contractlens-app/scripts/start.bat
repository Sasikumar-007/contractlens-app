@echo off
title ContractLens

cd /d "%~dp0..\backend"

if not exist ".env" (
    echo [ERROR] .env not found. Run setup.bat first.
    pause & exit /b 1
)

if not exist "uploads" mkdir uploads

echo.
echo  ContractLens is starting...
echo  Open your browser at: http://localhost:8000
echo  Press Ctrl+C to stop.
echo.

start "" "http://localhost:8000"
uvicorn main:app --reload --port 8000 --host 127.0.0.1
