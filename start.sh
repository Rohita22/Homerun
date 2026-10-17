#!/usr/bin/env bash
# One-command launcher: stops anything left over from a previous run, installs all
# dependencies, then starts the backend (FastAPI, :8000) followed by the frontend (Vite, :5173).
# Usage: ./start.sh      (Ctrl+C stops both)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
RUN_DIR="$ROOT/.run"
BACKEND_PORT=8000
FRONTEND_PORT=5173
PYTHON_BIN="${PYTHON_BIN:-python3}"

mkdir -p "$RUN_DIR"

log() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }

kill_port() {
  local pids
  pids="$(lsof -ti tcp:"$1" 2>/dev/null || true)"
  if [ -n "$pids" ]; then
    echo "Killing process(es) on port $1: $pids"
    # shellcheck disable=SC2086
    kill $pids 2>/dev/null || true
    sleep 1
    pids="$(lsof -ti tcp:"$1" 2>/dev/null || true)"
    # shellcheck disable=SC2086
    [ -n "$pids" ] && kill -9 $pids 2>/dev/null || true
  fi
}

stop_all() {
  # Previous runs of this script, plus stray uvicorn/vite processes from this project.
  for f in "$RUN_DIR"/backend.pid "$RUN_DIR"/frontend.pid; do
    [ -f "$f" ] && kill "$(cat "$f")" 2>/dev/null || true
    rm -f "$f"
  done
  pkill -f "$BACKEND/.venv/bin/uvicorn" 2>/dev/null || true
  pkill -f "$FRONTEND/node_modules/.bin/vite" 2>/dev/null || true
  kill_port "$BACKEND_PORT"
  kill_port "$FRONTEND_PORT"
}

cleanup() {
  trap - INT TERM EXIT
  echo; echo "Shutting down Homerun..."
  stop_all
}

wait_for() { # url name pid
  local i
  for i in $(seq 1 120); do
    curl -fs -o /dev/null "$1" && return 0
    kill -0 "$3" 2>/dev/null || { echo "$2 exited early. See logs in $RUN_DIR"; return 1; }
    sleep 1
  done
  echo "Timed out waiting for $2 ($1). See logs in $RUN_DIR"; return 1
}

command -v "$PYTHON_BIN" >/dev/null || { echo "python3 not found"; exit 1; }
command -v npm >/dev/null || { echo "npm (Node.js) not found"; exit 1; }

log "Stopping any running Homerun processes"
stop_all

log "Backend: virtualenv + dependencies"
cd "$BACKEND"
[ -d .venv ] || "$PYTHON_BIN" -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
[ -f .env ] || cp .env.example .env
mkdir -p data

if ! find . -name 'hdb_valuation_model.joblib' -not -path './.venv/*' | grep -q .; then
  log "Backend: training valuation model (first run)"
  HDB_ARG=()
  [ -f data/hdb_resale_live.csv ] && HDB_ARG=(--data-path data/hdb_resale_live.csv)
  python -m app.ml.train ${HDB_ARG[@]+"${HDB_ARG[@]}"}
fi

log "Frontend: npm install"
cd "$FRONTEND"
[ -f .env ] || cp .env.example .env
npm install --no-audit --no-fund

trap cleanup INT TERM EXIT

log "Starting backend on :$BACKEND_PORT"
cd "$BACKEND"
"$BACKEND/.venv/bin/uvicorn" app.main:app --host 127.0.0.1 --port "$BACKEND_PORT" \
  >"$RUN_DIR/backend.log" 2>&1 &
echo $! >"$RUN_DIR/backend.pid"
wait_for "http://127.0.0.1:$BACKEND_PORT/api/health" backend "$(cat "$RUN_DIR/backend.pid")"

log "Starting frontend on :$FRONTEND_PORT"
cd "$FRONTEND"
npm run dev -- --host 127.0.0.1 --port "$FRONTEND_PORT" --strictPort \
  >"$RUN_DIR/frontend.log" 2>&1 &
echo $! >"$RUN_DIR/frontend.pid"
wait_for "http://127.0.0.1:$FRONTEND_PORT" frontend "$(cat "$RUN_DIR/frontend.pid")"

cat <<MSG

  Homerun is running
    App:      http://localhost:$FRONTEND_PORT
    API docs: http://localhost:$BACKEND_PORT/docs
    Logs:     $RUN_DIR/backend.log, $RUN_DIR/frontend.log
  Press Ctrl+C to stop both.

MSG
command -v open >/dev/null && open "http://localhost:$FRONTEND_PORT" || true

wait
