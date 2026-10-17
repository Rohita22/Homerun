# Homerun

Explainable, multi-agent Singapore property discovery platform — IBM Z Datathon 2026 build.
See [`Homerun_Complete_PRD.pdf`](Homerun_Complete_PRD.pdf) for the full spec.

- [`backend/`](backend/) — FastAPI + SQLite + scikit-learn backend implementing the PRD's P0
  scope (five agents, orchestrator, HDB valuation model, handoff state machine, full API).
- [`frontend/design/Homerun.html`](frontend/design/Homerun.html) — the product design (the source of
  truth for every screen). [`frontend/app/`](frontend/app/) builds it into the served UI: markup and
  styling are the design's, only its mock data is replaced by calls to the backend.
- [`frontend/src/`](frontend/src/) — the earlier minimal React/Vite test client (superseded; kept for
  reference).

## Run it

```bash
./start.sh            # builds the UI, installs deps, starts everything on http://localhost:8000
```

That one port serves the UI (`/`), the API (`/api`) and Swagger (`/docs`). The first run installs the
backend dependencies and trains the HDB valuation model on the resale dataset.

The listing data is **scraped PropertyGuru data only** (no demo/fixture listings in the app):

```bash
cd backend && source .venv/bin/activate
python -m app.scraper --targets "hdb-for-sale:30,condo-for-sale:15"   # needs Playwright (macOS/x86 Linux)
python -m app.scraper --geocode-only                                   # fills coordinates (map + commute)
```

The server also re-scrapes on a timer (`SCRAPE_INTERVAL_HOURS`, default 12) when `SCRAPE_ENABLED=true`.

## Deploy to the IBM LinuxONE (s390x) VM

```bash
deploy/deploy.sh <user>@<host> --key backend/homerun1.pem --push
```

Syncs the backend + built UI to `/opt/homerun`, installs numpy/pandas/scikit-learn from `apt`
(PyPI has no s390x wheels), trains the valuation model on the VM, installs the `homerun-backend`
systemd unit and opens port 8000. **Chromium has no s390x build, so the VM cannot scrape**: scrape on
your Mac/Linux box and `--push` (or `python -m app.scraper --push-only http://<host>:8000 --token
<ADMIN_TOKEN>`) to ship the listings to it. Details in [`backend/README.md`](backend/README.md).

## Currently live

- **Deployed on real IBM Z hardware**: `http://148.100.77.89:8000/api/health` (confirms
  `architecture: s390x`) / `http://148.100.77.89:8000/docs`. See `backend/README.md` →
  "Deployment to IBM Z / LinuxONE" for how it got there.
- **Live listing data**: `LISTING_PROVIDER=authorized` pulls real PropertyGuru Singapore
  listings via a working Parse.bot connector (`source_mode: "live_authorized"` in the API
  response) — see `backend/README.md` → "Live listing data" for the daily-quota caveat.
- **ML**: the HDB valuation model trains on the real, live data.gov.sg resale dataset (~243k
  transactions) with conformalized quantile regression intervals — see `backend/README.md` →
  "ML".
- **Agent orchestration trace**: every `/api/chat`, `/api/recommendations`, `/api/feedback`, and
  `/api/finance/estimate` response includes a `trace` array (per-agent status/timing/model
  version), rendered live in the frontend under each screen.
