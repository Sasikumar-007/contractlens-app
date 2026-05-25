#!/bin/bash
echo "================================================"
echo " ContractLens — Starting Application"
echo "================================================"
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/../backend" || exit 1

if [ ! -f ".env" ]; then
    echo "❌ ERROR: .env file not found!"
    echo "   Run: cp .env.example .env"
    echo "   Then fill in your OPENAI_API_KEY and SUPABASE_DB_URL"
    exit 1
fi

echo "📦 Installing dependencies..."
pip install -r requirements.txt -q

echo ""
echo "🚀 Starting ContractLens..."
echo "   Open: http://localhost:8000"
echo "   API docs: http://localhost:8000/api/docs"
echo "   Press Ctrl+C to stop"
echo ""

uvicorn main:app --reload --port 8000 --host 0.0.0.0
