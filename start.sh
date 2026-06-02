#!/bin/bash
# Quick start script — runs both backend and frontend for local testing

set -e

echo "╔══════════════════════════════════════════╗"
echo "║   LinkedIn Post Generator — Local Dev    ║"
echo "╚══════════════════════════════════════════╝"
echo ""

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

# ─── Backend setup ────────────────────────────────────────────
echo "→ Setting up backend..."
cd backend

if [ ! -d "venv" ]; then
    echo "  Creating virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate
echo "  Installing Python dependencies..."
pip install -r requirements.txt --quiet

if [ ! -f ".env" ]; then
    echo "  Creating .env from template..."
    cp .env.example .env
    echo ""
    echo "⚠️  IMPORTANT: Add your API keys to backend/.env"
    echo "   - OPENROUTER_API_KEY (get from openrouter.ai)"
    echo "   - TAVILY_API_KEY (get from tavily.com)"
    echo "   Both have free tiers."
    echo ""
fi

# Start backend in background
echo "  Starting FastAPI on http://localhost:8000..."
python -m uvicorn api.main:app --reload --port 8000 &
BACKEND_PID=$!
cd ..

# ─── Frontend setup ──────────────────────────────────────────
echo "→ Setting up frontend..."
cd frontend

if [ ! -d "node_modules" ]; then
    echo "  Installing npm dependencies..."
    npm install --quiet
fi

echo "  Starting Vite on http://localhost:5173..."
npm run dev &
FRONTEND_PID=$!
cd ..

echo ""
echo "✅ Both servers running!"
echo "   Frontend: http://localhost:5173"
echo "   Backend:  http://localhost:8000"
echo "   API docs: http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop both servers."

# Cleanup on exit
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; echo ''; echo 'Servers stopped.'" EXIT

# Wait
wait
