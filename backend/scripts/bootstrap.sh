#!/usr/bin/env bash
# Bootstraps the Homerun backend (PRD section 9 deployment requirements + section 15 "Provision
# SSH/s390x, env smoke test"). Idempotent: safe to re-run.
#
# On IBM Z / LinuxONE (s390x) PyPI has no wheels for numpy/pandas/scikit-learn/scipy, so those four
# come from apt and the venv inherits them (--system-site-packages); everything else is pip-installed
# from requirements-server.txt. Elsewhere the full requirements.txt (with Playwright) is used.
set -euo pipefail

cd "$(dirname "$0")/.."

ARCH="$(uname -m)"
echo "== Architecture: $ARCH (expect s390x on the real LinuxONE host) =="
uname -a

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_ARGS=()
REQS="requirements.txt"
if [ "$ARCH" = "s390x" ]; then
  REQS="requirements-server.txt"
  VENV_ARGS=(--system-site-packages)
  echo "== s390x: installing numpy/pandas/scikit-learn/scipy from apt =="
  if ! "$PYTHON_BIN" -c "import numpy, pandas, sklearn, scipy" 2>/dev/null; then
    sudo apt-get update -y
    sudo apt-get install -y python3-venv python3-pip python3-numpy python3-pandas python3-sklearn python3-scipy sqlite3
  fi
fi

echo "== Creating virtualenv (.venv) =="
[ -d .venv ] || "$PYTHON_BIN" -m venv ${VENV_ARGS[@]+"${VENV_ARGS[@]}"} .venv
# shellcheck disable=SC1091
source .venv/bin/activate

echo "== Installing dependencies ($REQS) =="
pip install --upgrade pip
pip install -r "$REQS"

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

echo "== Creating tables =="
python -c "from app.db.base import init_db; init_db()"

echo "== HDB valuation model =="
# A model pickled under a different scikit-learn version is unreliable, so it is trained on the
# machine that serves it (skipped when one is already there; RETRAIN=1 forces it).
if [ -f app/ml/artifacts/hdb_valuation_model.joblib ] && [ "${RETRAIN:-0}" != "1" ]; then
  echo "model artifact present; skipping training (RETRAIN=1 to force)"
elif [ -n "${HDB_CSV:-}" ]; then
  python -m app.ml.train --data-path "$HDB_CSV"
elif [ -f data/hdb_resale_live.csv ]; then
  python -m app.ml.train --data-path data/hdb_resale_live.csv
else
  python -m app.ml.train
fi

echo "== Running test suite =="
pytest -q || echo "WARNING: tests failed (or pytest is not installed); review before deploying."

echo "== Done. Start the API (it also serves the UI from FRONTEND_DIR) with: =="
echo "    source .venv/bin/activate && uvicorn app.main:app --host 0.0.0.0 --port 8000"
echo "== Or install the systemd unit at scripts/homerun-backend.service =="
