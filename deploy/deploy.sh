#!/usr/bin/env bash
# Deploy Homerun (API + UI) to an IBM LinuxONE / s390x Ubuntu VM over SSH. Idempotent: re-running
# updates the code and restarts the service, keeping the VM's .env and database.
#
#   deploy/deploy.sh user@host [--key backend/homerun1.pem] [--port 8000] [--retrain] [--push]
#
#   --push     after deploying, send the locally scraped listings to the VM (the VM cannot scrape:
#              Chromium has no s390x build). Needs a local scrape first: python -m app.scraper
#   --retrain  retrain the HDB valuation model on the VM
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="${1:?usage: deploy/deploy.sh user@host [--key file] [--port N] [--retrain] [--push]}"
shift
KEY="$ROOT/backend/homerun1.pem"; PORT=8000; PUSH=0; RETRAIN=0
while [ $# -gt 0 ]; do
  case "$1" in
    --key) KEY="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    --push) PUSH=1; shift ;;
    --retrain) RETRAIN=1; shift ;;
    *) echo "unknown option: $1"; exit 2 ;;
  esac
done
HOST="${TARGET#*@}"
REMOTE=/opt/homerun
chmod 600 "$KEY"
SSH_OPTS=(-i "$KEY" -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=30 -o ConnectTimeout=20)
rssh() { ssh "${SSH_OPTS[@]}" "$TARGET" "$@"; }
log() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }

log "Building the UI"
python3 "$ROOT/frontend/app/build.py"

log "Connecting to $TARGET"
rssh 'echo "user:   $(id -un)"; echo "arch:   $(uname -m)"; . /etc/os-release; echo "os:     $PRETTY_NAME"; echo "cpus:   $(nproc)"; sudo -n true 2>/dev/null && echo "sudo:   ok" || echo "sudo:   NEEDS PASSWORD"'
ARCH="$(rssh 'uname -m')"
[ "$ARCH" = "s390x" ] || echo "NOTE: expected s390x for LinuxONE, this host is $ARCH (deploying anyway)"
SVC_USER="$(rssh 'id -un')"

log "Preparing $REMOTE"
rssh "sudo mkdir -p $REMOTE/backend $REMOTE/frontend/app && sudo chown -R $SVC_USER: $REMOTE"
rssh 'command -v rsync >/dev/null || sudo apt-get install -y rsync >/dev/null'

log "Syncing backend + UI"
RSYNC=(rsync -az --delete -e "ssh ${SSH_OPTS[*]}")
"${RSYNC[@]}" \
  --exclude '.venv/' --exclude '__pycache__/' --exclude '*.pyc' --exclude '.pytest_cache/' \
  --exclude '.env' --exclude '*.pem' --exclude 'tests/' \
  --exclude 'data/*.db' --exclude 'data/*.db-*' --exclude 'app/ml/artifacts/*.joblib' \
  "$ROOT/backend/" "$TARGET:$REMOTE/backend/"
"${RSYNC[@]}" "$ROOT/frontend/app/dist/" "$TARGET:$REMOTE/frontend/app/dist/"

log "Configuring .env (keeps existing values; fills what the VM needs)"
if ! rssh "test -f $REMOTE/backend/.env"; then
  scp "${SSH_OPTS[@]}" -q "$ROOT/backend/.env" "$TARGET:$REMOTE/backend/.env"
fi
SHA="$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo dev)"
rssh "REMOTE=$REMOTE SHA=$SHA PORT=$PORT python3 - <<'PY'
import os, pathlib, secrets, re
env = pathlib.Path(os.environ['REMOTE'], 'backend', '.env')
lines = env.read_text().splitlines() if env.exists() else []
vals = {}
for i, line in enumerate(lines):
    m = re.match(r'^([A-Z0-9_]+)=(.*)$', line)
    if m: vals[m.group(1)] = i
def setv(key, value, only_if_missing=False):
    if key in vals:
        if only_if_missing: return
        lines[vals[key]] = f'{key}={value}'
    else:
        vals[key] = len(lines); lines.append(f'{key}={value}')
setv('HOMERUN_ENV', 'production'); setv('HOMERUN_DEBUG', 'false')
setv('LISTING_PROVIDER', 'scraped'); setv('SCRAPE_ENABLED', 'false')   # VM cannot run Chromium
setv('FRONTEND_DIR', os.environ['REMOTE'] + '/frontend/app/dist')
setv('HOMERUN_BUILD_SHA', os.environ['SHA'])
setv('HOMERUN_DATABASE_URL', 'sqlite:///' + os.environ['REMOTE'] + '/backend/data/homerun.db')
setv('HOMERUN_CORS_ORIGINS', 'http://localhost:' + os.environ['PORT'])
setv('ADMIN_TOKEN', secrets.token_hex(24), only_if_missing=True)
cur = lines[vals['HOMERUN_SECRET_KEY']].split('=', 1)[1] if 'HOMERUN_SECRET_KEY' in vals else ''
if not cur or cur.startswith('change-me'): setv('HOMERUN_SECRET_KEY', secrets.token_hex(32))
env.write_text('\n'.join(lines) + '\n'); env.chmod(0o600)
PY"

log "Installing dependencies + training the valuation model on the VM (first run takes a while)"
rssh "cd $REMOTE/backend && RETRAIN=$RETRAIN PYTHON_BIN=python3 bash scripts/bootstrap.sh"

log "Installing the systemd service"
sed "s/__SERVICE_USER__/$SVC_USER/" "$ROOT/backend/scripts/homerun-backend.service" \
  | rssh 'sudo tee /etc/systemd/system/homerun-backend.service >/dev/null'
rssh 'sudo systemctl daemon-reload && sudo systemctl enable homerun-backend >/dev/null 2>&1 && sudo systemctl restart homerun-backend'

log "Opening port $PORT in the host firewall"
rssh "sudo iptables -C INPUT -p tcp --dport $PORT -m conntrack --ctstate NEW -j ACCEPT 2>/dev/null || sudo iptables -I INPUT 2 -p tcp --dport $PORT -m conntrack --ctstate NEW -j ACCEPT; sudo mkdir -p /etc/iptables && sudo bash -c 'iptables-save > /etc/iptables/rules.v4'"  # LinuxONE Ubuntu persists rules here

log "Waiting for the service"
for i in $(seq 1 40); do
  if rssh "curl -fs http://127.0.0.1:$PORT/api/health" > /tmp/homerun_health.json 2>/dev/null; then break; fi
  sleep 3
done
cat /tmp/homerun_health.json 2>/dev/null || { echo "service did not come up:"; rssh 'sudo journalctl -u homerun-backend -n 40 --no-pager'; exit 1; }
echo

if [ "$PUSH" = 1 ]; then
  log "Pushing the locally scraped listings to the VM"
  TOKEN="$(rssh "grep '^ADMIN_TOKEN=' $REMOTE/backend/.env | cut -d= -f2")"
  URL="http://$HOST:$PORT"
  if ! curl -fs -m 8 "$URL/api/health" >/dev/null 2>&1; then
    echo "port $PORT is not reachable from here (cloud firewall?); using an SSH tunnel"
    ssh "${SSH_OPTS[@]}" -fN -L 18000:127.0.0.1:$PORT "$TARGET"
    URL="http://127.0.0.1:18000"
    trap 'pkill -f "18000:127.0.0.1:$PORT" 2>/dev/null || true' EXIT
  fi
  (cd "$ROOT/backend" && .venv/bin/python -m app.scraper --push-only "$URL" --token "$TOKEN")
fi

cat <<MSG

  Homerun is deployed.
    App:      http://$HOST:$PORT
    API docs: http://$HOST:$PORT/docs
    Health:   http://$HOST:$PORT/api/health   (architecture should read s390x)
    Logs:     ssh -i $KEY $TARGET 'sudo journalctl -u homerun-backend -f'
  If the page is unreachable from outside, open TCP $PORT in the VM's cloud security group too.

MSG
