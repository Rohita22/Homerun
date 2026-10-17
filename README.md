# Homerun

Explainable, multi-agent Singapore property discovery platform — IBM Z Datathon 2026 build.

- [`backend/`](backend/) — FastAPI + SQLite + scikit-learn backend: five agents, an orchestrator, an
  HDB valuation model, a handoff state machine, voice AI and the full API.
- [`frontend/design/Homerun.html`](frontend/design/Homerun.html) — the product design (the source of
  truth for every screen). [`frontend/app/`](frontend/app/) builds it into the served UI: markup and
  styling are the design's, only its mock data is replaced by calls to the backend.
- [`frontend/src/`](frontend/src/) — the earlier minimal React/Vite test client (superseded; kept for
  reference).
- [`deploy/`](deploy/) — deployment script for an IBM LinuxONE (s390x) VM.

## Features

- **Multi-agent pipeline** — Buyer Intelligence, Market Intelligence, Valuation, Affordability and
  Matching/Decision agents, coordinated by an orchestrator. Every `/api/chat`, `/api/recommendations`,
  `/api/feedback` and `/api/finance/estimate` response includes a `trace` array (per-agent
  status/timing/model version), which the frontend renders under each screen.
- **Buyer journey** — describe what you want in chat or by voice, review the preferences learned,
  get ranked and explained matches, compare properties, book viewings and hand off to an agent with
  explicit consent.
- **Voice AI** — spoken conversation powered by Gemini Live (needs `GEMINI_API_KEY`).
- **Explanations** — Gemini (or Groq) when an API key is set, otherwise a deterministic template
  provider that works fully offline.
- **ML valuation** — the HDB valuation model is trained on the live data.gov.sg resale dataset
  (~243k transactions) with conformalized quantile regression intervals.
- **Listing data** — scraped PropertyGuru data (HDB and condo), with geocoding for the map and
  commute features.

Details for each area are in [`backend/README.md`](backend/README.md).

## Run it

```bash
./start.sh            # builds the UI, installs deps, starts everything on http://localhost:8000
```

That one port serves the UI (`/`), the API (`/api`) and Swagger (`/docs`). The first run creates
`backend/.env` from `backend/.env.example`, installs the backend dependencies and trains the HDB
valuation model on the resale dataset.

## Configuration

Settings live in `backend/.env` (copied from [`backend/.env.example`](backend/.env.example)). The
app runs with no keys at all; add them to enable more:

| Setting | Purpose |
| --- | --- |
| `LLM_PROVIDER` | `template` (default, offline), `gemini` or `groq` |
| `GEMINI_API_KEY` | Gemini explanations and Gemini Live voice AI |
| `GROQ_API_KEY` | Groq as an alternative LLM provider |
| `LISTING_PROVIDER` | `scraped` (default), `demo_fixture` (offline) or `authorized` |
| `SCRAPE_*` | Scraper schedule, targets and limits |

## Listing data

The app serves **scraped PropertyGuru listings**. Scrape manually with:

```bash
cd backend && source .venv/bin/activate
python -m app.scraper --targets "hdb-for-sale:30,condo-for-sale:15"   # needs Playwright (macOS/x86 Linux)
python -m app.scraper --geocode-only                                   # fills coordinates (map + commute)
```

When `SCRAPE_ENABLED=true` the server also re-scrapes on a timer: a quick scrape every
`SCRAPE_INTERVAL_HOURS` (default 1) and a full scrape every `SCRAPE_FULL_EVERY_HOURS` (default 12).
Listings not seen for `SCRAPE_STALE_AFTER_HOURS` (default 72) are treated as stale.

## Tests

```bash
cd backend && source .venv/bin/activate
pytest -q
```

## Deploy to an IBM LinuxONE (s390x) VM

```bash
deploy/deploy.sh <user>@<host> --key <path-to-key.pem> --push
```

Syncs the backend and built UI to `/opt/homerun`, installs numpy/pandas/scikit-learn from `apt`
(PyPI has no s390x wheels), trains the valuation model on the VM, installs the `homerun-backend`
systemd unit and opens port 8000. **Chromium has no s390x build, so the VM cannot scrape**: scrape on
your Mac/Linux machine and `--push` (or `python -m app.scraper --push-only http://<host>:8000 --token
<ADMIN_TOKEN>`) to ship the listings to it. `GET /api/health` on the deployed instance reports its
`architecture` (`s390x` on IBM Z). Full details are in [`backend/README.md`](backend/README.md) →
"Deployment to IBM Z / LinuxONE".
