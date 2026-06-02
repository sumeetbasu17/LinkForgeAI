#!/bin/bash
# ─── LinkedIn Post Generator — Local Dev Startup ─────────────────
# Run this from the project root: ./scripts/dev.sh

set -e

echo "🚀 LinkedIn Post Generator — Local Development"
echo "================================================"

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 not found. Install Python 3.11+"
    exit 1
fi

# Check Node
if ! command -v node &> /dev/null; then
    echo "❌ Node.js not found. Install Node 18+"
    exit 1
fi

# Backend setup
echo ""
echo "📦 Setting up backend..."
cd backend

if [ ! -d "venv" ]; then
    echo "  Creating virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate
echo "  Installing dependencies..."
pip install -r requirements.txt -q

if [ ! -f ".env" ]; then
    echo "  ⚠️  No .env file found. Copying from .env.example..."
    cp .env.example .env
    echo "  📝 Please edit backend/.env and add your API keys:"
    echo "     - OPENROUTER_API_KEY (get from openrouter.ai)"
    echo "     - TAVILY_API_KEY (get from tavily.com)"
    echo ""
fi

# Create data directory for LanceDB
mkdir -p data/lancedb

echo "  Starting backend on http://localhost:8000..."
python -m uvicorn api.main:app --reload --port 8000 &
BACKEND_PID=$!

cd ..

# Frontend setup
echo ""
echo "📦 Setting up frontend..."
cd frontend

if [ ! -d "node_modules" ]; then
    echo "  Installing dependencies..."
    npm install
fi

echo "  Starting frontend on http://localhost:5173..."
npm run dev &
FRONTEND_PID=$!

cd ..

echo ""
echo "================================================"
echo "✅ Both servers running!"
echo "   Frontend: http://localhost:5173"
echo "   Backend:  http://localhost:8000"
echo "   API docs: http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop both servers."
echo "================================================"

# Wait for Ctrl+C
trap "echo ''; echo 'Stopping...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" SIGINT
wait
