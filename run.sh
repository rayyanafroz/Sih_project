#!/usr/bin/env bash
# AICTE VerifyAI — one-command launcher.
#   ./run.sh           set up if needed, then serve the app at http://127.0.0.1:8000
#   ./run.sh --reset   also reset the database to the demo state before starting
#   ./run.sh --dev     run API (:8000) + Vite dev server with hot reload (:5173)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
PORT="${PORT:-8000}"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
PY="$BACKEND/.venv/bin/python"

if [ ! -x "$PY" ]; then
  echo "→ Creating Python virtualenv and installing backend dependencies"
  python3 -m venv "$BACKEND/.venv"
  "$PY" -m pip install -q --upgrade pip
  "$PY" -m pip install -q -r "$BACKEND/requirements.txt"
fi

if [ ! -d "$FRONTEND/node_modules" ]; then
  echo "→ Installing frontend dependencies"
  (cd "$FRONTEND" && npm install --silent)
fi

if ! command -v tesseract >/dev/null 2>&1 && [ ! -x "$HOME/.local/bin/tesseract" ]; then
  echo "⚠ Tesseract OCR not found — scanned documents will be routed to manual review."
  echo "  Install: sudo pacman -S tesseract tesseract-data-eng | sudo apt install tesseract-ocr | brew install tesseract"
fi

# Seed on --reset, or whenever the database has no users (first run, or an earlier run that stopped part-way).
if [[ " $* " == *" --reset "* ]] || ! (cd "$BACKEND" && "$PY" -m scripts.has_users); then
  echo "→ Setting up the database with the demo data"
  (cd "$BACKEND" && "$PY" -m scripts.reset_demo)
fi

if [[ " $* " == *" --dev "* ]]; then
  echo "→ Dev mode: API on :8000, UI with hot reload on http://localhost:5173"
  (cd "$BACKEND" && "$PY" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000) &
  API_PID=$!
  trap 'kill $API_PID 2>/dev/null' EXIT
  cd "$FRONTEND" && npm run dev
else
  echo "→ Building frontend"
  (cd "$FRONTEND" && npm run build --silent >/dev/null)
  echo "→ AICTE VerifyAI running at http://127.0.0.1:$PORT  (Ctrl+C to stop)"
  cd "$BACKEND" && exec "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT"
fi
