# Homerun

Explainable, multi-agent Singapore property discovery platform — IBM Z Datathon 2026 build.
See [`Homerun_Complete_PRD.pdf`](Homerun_Complete_PRD.pdf) for the full spec.

- [`backend/`](backend/) — FastAPI + SQLite + scikit-learn backend implementing the PRD's P0
  scope (five agents, orchestrator, HDB valuation model, handoff state machine, full API).
- [`frontend/`](frontend/) — minimal React/Vite client for manually testing the backend's real
  flow end to end.

## Run both

```bash
# Terminal 1 — backend (first run: ./backend/scripts/bootstrap.ps1 or bootstrap.sh)
cd backend
.\.venv\Scripts\uvicorn.exe app.main:app --reload     # Windows
# source .venv/bin/activate && uvicorn app.main:app --reload   # Linux/LinuxONE

# Terminal 2 — frontend
cd frontend
npm install   # first time only
npm run dev
```

Then open **http://localhost:5173** for the app, or **http://localhost:8000/docs** for the raw
API (Swagger UI) — both talk to the same backend.

Each directory has its own README with architecture notes, the SOLID mapping, the full API
contract, and deployment instructions for the IBM Z / LinuxONE target.

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
