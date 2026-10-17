#!/usr/bin/env bash
# One-command local launcher: builds the Homerun UI from the design, then starts the backend, which
# serves both the API and the UI on one port.
# Usage: ./start.sh      (Ctrl+C stops it)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND="$ROOT/backend"
RUN_DIR="$ROOT/.run"
PORT="${PORT:-8000}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

mkdir -p "$RUN_DIR"
log() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }

command -v "$PYTHON_BIN" >/dev/null || { echo "python3 not found"; exit 1; }

log "Stopping anything already listening on :$PORT"
pids="$(lsof -ti tcp:"$PORT" 2>/dev/null || true)"
# shellcheck disable=SC2086
[ -n "$pids" ] && kill $pids 2>/dev/null || true
sleep 1

log "Building the UI (design + backend wiring)"
"$PYTHON_BIN" "$ROOT/frontend/app/build.py"

log "Backend: virtualenv + dependencies"
cd "$BACKEND"
[ -d .venv ] || "$PYTHON_BIN" -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
[ -f .env ] || cp .env.example .env
mkdir -p data
playwright install chromium >/dev/null 2>&1 || echo "(Playwright browser not installed: scraping disabled on this machine)"

if ! find . -name 'hdb_valuation_model.joblib' -not -path './.venv/*' | grep -q .; then
  log "Backend: training valuation model (first run)"
  HDB_ARG=()
  [ -f data/hdb_resale_live.csv ] && HDB_ARG=(--data-path data/hdb_resale_live.csv)
  python -m app.ml.train ${HDB_ARG[@]+"${HDB_ARG[@]}"}
fi

log "Starting Homerun on :$PORT"
cat <<MSG

  App:      http://localhost:$PORT
  API docs: http://localhost:$PORT/docs
  Scrape:   python -m app.scraper   (from backend/, venv active)
  Press Ctrl+C to stop.

MSG
command -v open >/dev/null && (sleep 3; open "http://localhost:$PORT") &
exec uvicorn app.main:app --host 127.0.0.1 --port "$PORT"
