#!/usr/bin/env bash
# Bootstraps the Homerun backend on the IBM Z / LinuxONE VM (PRD section 9 deployment
# requirements + section 15 "0-3h: Provision SSH/s390x, env smoke test"). Idempotent: safe to
# re-run.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "== Architecture check (expect s390x on the real LinuxONE host) =="
uname -m
uname -a

PYTHON_BIN="${PYTHON_BIN:-python3}"

echo "== Creating virtualenv (.venv) =="
"$PYTHON_BIN" -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate

echo "== Installing pinned dependencies =="
pip install --upgrade pip
pip install -r requirements.txt

echo "== Package compatibility smoke test =="
python - <<'PY'
import fastapi, sqlalchemy, sklearn, pandas, numpy, uvicorn
print("fastapi", fastapi.__version__)
print("sqlalchemy", sqlalchemy.__version__)
print("scikit-learn", sklearn.__version__)
print("pandas", pandas.__version__)
print("numpy", numpy.__version__)
PY

if [ ! -f .env ]; then
  echo "== Creating .env from .env.example =="
  cp .env.example .env
fi

mkdir -p data

echo "== Bootstrapping database + demo fixture catalog =="
python -c "from app.bootstrap import bootstrap; bootstrap()"

echo "== Training HDB valuation model (synthetic bootstrap unless HDB_CSV is set) =="
if [ -n "${HDB_CSV:-}" ]; then
  python -m app.ml.train --data-path "$HDB_CSV"
else
  python -m app.ml.train
fi

echo "== Running test suite =="
pytest -q || echo "WARNING: tests failed; review before deploying."

echo "== Done. Start the API with: =="
echo "    source .venv/bin/activate && uvicorn app.main:app --host 0.0.0.0 --port 8000"
echo "== Or install the systemd unit at scripts/homerun-backend.service =="
