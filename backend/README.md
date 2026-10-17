# Homerun backend

FastAPI backend for **Homerun** — an explainable, multi-agent Singapore property discovery
platform (IBM Z Datathon 2026). Implements the P0 scope of the PRD: buyer chat → structured
preferences → five-agent orchestration → ranked shortlist → HDB valuation → affordability →
compare → feedback reranking → consented, verified agent handoff.

This backend is framework-agnostic on the frontend side: it's a stateless JSON API any client
(React/Vite, Streamlit, mobile) can call directly. See [Connecting a frontend](#connecting-a-frontend).

## Quickstart (local dev)

```powershell
cd backend
.\scripts\bootstrap.ps1            # creates venv, installs deps, bootstraps DB, trains model, runs tests
.\.venv\Scripts\uvicorn.exe app.main:app --reload
```

```bash
# Linux / LinuxONE (s390x)
cd backend
./scripts/bootstrap.sh
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Then open http://localhost:8000/docs for the interactive OpenAPI UI, or:

```bash
curl http://localhost:8000/api/health
```

## Architecture

```
Browser / Frontend
      │ HTTPS (CORS-enabled JSON)
      ▼
FastAPI app (app/main.py)
      │  RequestContextMiddleware (request_id, latency, metrics)
      ▼
API routes (app/api/routes/*)  ──depends on──►  app/api/deps.py (composition root)
      │                                               │
      ▼                                               ▼
Orchestrator (app/orchestration)         Agents (app/agents/*) ──► Services (app/services/*)
      │  extract→validate→retrieve→enrich→value→(finance)→rank→explain
      ▼
Repositories (app/repositories/*) ──► SQLAlchemy models (app/db/models.py) ──► SQLite (WAL)
      │
      ▼
Providers (app/providers/*) implementing domain interfaces (app/domain/interfaces/*)
  - ListingProvider: DemoFixtureProvider (default, offline) | AuthorizedProvider (Parse.bot, disabled)
  - LLMProvider: TemplateLLMProvider (default, offline) | GeminiLLMProvider
  - ValuationModel: ValuationService (trained HistGradientBoostingRegressor, falls back to
    comparable-sales median baseline) — app/ml/*
```

### The five agents (PRD section 5)

| # | Agent | File | Responsibility |
|---|-------|------|-----------------|
| 1 | Buyer Intelligence | `app/agents/buyer_intelligence.py` | free text → `BuyerProfile` patch via `LLMProvider` |
| 2 | Market Intelligence | `app/agents/market_intelligence.py` | deterministic hard-constraint filtering → `CandidateSet` |
| 3 | Valuation | `app/agents/valuation_agent.py` | HDB-only price estimate + interval via `ValuationModel` |
| 4 | Affordability & Risk | `app/agents/affordability_agent.py` | mortgage math + stress scenarios |
| 5 | Matching & Decision | `app/agents/matching_decision_agent.py` | multiobjective ranking, diversity, rationale |

Every agent returns a typed `AgentResult` (`request_id`, `status`, `data`, `evidence_refs`,
`warnings`, `elapsed_ms`, `model_version`) — see `app/domain/entities.py`. The
`RecommendationOrchestrator` (`app/orchestration/orchestrator.py`) runs them in the PRD's
documented order and persists each run so it's auditable.

### SOLID, concretely

- **Single Responsibility** — each agent does one job; ranking, finance math, consent policy and
  handoff state transitions each live in their own `app/services/*` module instead of being
  inlined into route handlers.
- **Open/Closed** — adding a new listing provider or LLM provider means writing one new class
  that satisfies `ListingProvider`/`LLMProvider` (`app/domain/interfaces/`) and pointing
  `LISTING_PROVIDER`/`LLM_PROVIDER` at it; no existing code changes.
- **Liskov Substitution** — `DemoFixtureProvider` and `AuthorizedListingProvider` are fully
  interchangeable behind `ListingProvider`; same for the two `LLMProvider`s and the baseline vs.
  trained `ValuationModel`.
- **Interface Segregation** — `ListingProvider`, `LLMProvider` and `ValuationModel` are separate,
  minimal `Protocol`s instead of one god-interface.
- **Dependency Inversion** — routes depend on `app/api/deps.py` factories, which depend on
  abstractions; the only place concrete classes are constructed is in `deps.py` and the
  `app/providers/*/factory.py` modules (the composition root).

### Database (PRD section 10)

SQLite in WAL mode (`app/db/base.py`); tables created via `Base.metadata.create_all` at startup
(`app/bootstrap.py`) — no Alembic migration tooling for hackathon speed, matching PRD section 9.
Swap `HOMERUN_DATABASE_URL` to a `postgresql://` DSN for production; nothing else changes.

### ML (PRD section 7C)

- `app/ml/features.py` — shared feature schema (town, flat_type, floor_area_sqm, storey_range,
  flat_model, remaining_lease_years, transaction_month).
- `app/ml/baseline_model.py` — comparable-sales median baseline (and the always-available
  fallback when no trained artifact exists).
- `app/ml/hgb_model.py` — three `HistGradientBoostingRegressor` pipelines: a point estimate
  (squared-error loss) plus a lower/upper conditional-quantile pair, combined with
  **conformalized quantile regression (CQR)** — a single scalar margin fit on held-out validation
  conformity scores — for a distribution-free coverage guarantee on the prediction interval. This
  replaced a flatter, constant-width residual-shift calibration because real uncertainty isn't
  the same for a common 4-room Tampines flat as for a rare Executive flat in a thin market.
- `app/ml/train.py` — chronological train/val/test split (no future leakage), fits all three
  pipelines, computes permutation feature importance, optionally runs a bounded
  `RandomizedSearchCV` hyperparameter search (`--tune`), evaluates against the baseline, and saves
  the artifact + a reproducible metrics JSON. Run it with a real `data.gov.sg` HDB resale CSV —
  `scripts/fetch_hdb_resale_data.py` pulls the **real, live, public** dataset (no API key needed;
  resource `d_8b84c4ee58e3cfc0ece0d773c8ca6abc`, ~243k transactions since 2017) straight from
  data.gov.sg's API:

  ```bash
  python scripts/fetch_hdb_resale_data.py                     # writes data/hdb_resale_live.csv
  python -m app.ml.train --data-path data/hdb_resale_live.csv [--tune]
  ```

  Omit `--data-path` to bootstrap from a deterministic synthetic dataset (seeded, clearly labeled
  `is_synthetic_training_data: true` in the saved metrics) so the whole system is runnable and
  testable completely offline. Trained on the real dataset, the HGB model's test-set MAE is
  ~62% lower than the comparable-sales median baseline (`beats_baseline: true` in
  `hdb_valuation_metrics.json`). **Honesty note**: tree-based models can't extrapolate price
  drift past the training window, so the interval's *measured* empirical coverage on the test
  period is noticeably below its 80% nominal target — this is disclosed in the metrics JSON and
  in the API's `coverage_note` rather than papered over.
- Condos/landed/EC never get an HDB valuation — `ValuationService.is_supported` gates on
  `property_type == "HDB"`, so the orchestrator never calls the model for them and the API
  returns `status: "unsupported_property_type"` instead.

### Scraped PropertyGuru listings (`LISTING_PROVIDER=scraped`, free, no API quota)

A Playwright scraper (`app/scraper/`) reads PropertyGuru's public search-result pages, normalizes
each card (`parser.py`) and upserts it into the same `properties` table everything else reads.
Buyer requests never touch the network; they only read the DB.

- **Schedule**: the API process scrapes every `SCRAPE_INTERVAL_HOURS` (default 12) via
  `app/scraper/scheduler.py`. Due-ness comes from the `scrape_runs` table, so restarts neither skip
  nor repeat a run; a fully failed run is retried after 1h. Manual run / cron:
  `python -m app.scraper [--if-due] [--headed] [--targets "hdb-for-sale:2"]`.
- **Targets**: `SCRAPE_TARGETS="hdb-for-sale:30,condo-for-sale:20"` (path:pages,
  20 listings per page). A full default run is about 60 page loads, roughly 15 minutes.
- **Cloudflare**: PropertyGuru challenges a browser session that keeps navigating, and any query
  string (even `?sort=`). So every page uses a fresh browser, plain paths, delays with jitter, and
  retry with backoff. A page that stays blocked is skipped and counted in `scrape_runs`; there is no
  stealth/proxy/CAPTCHA evasion by design.
- **Towns**: the HDB town is looked up from `(block, street)` in `data/hdb_resale_live.csv`; the area
  label is only used when it names a single town. Ambiguous (mostly condo) listings keep
  `town=NULL` and show up as "needs confirmation" instead of being guessed.
- **Staleness**: listings not re-seen for `SCRAPE_STALE_AFTER_HOURS` (72) are marked inactive.
- **Not available from result cards**: storey range, flat model, agent phone/email (handoff falls
  back to the original listing link). Remaining lease is estimated from build year and labelled so.
- **Caveats**: PropertyGuru's terms restrict scraping; this is for the demo, and the UI says when
  listings were last refreshed. Playwright has no Chromium build for s390x, so on the IBM Z server
  run the scraper elsewhere against a shared DB, or switch to Postgres.

### Live listing data (PRD section 6 / 16)

`LISTING_PROVIDER=authorized` wires up `app/providers/listing/authorized_provider.py` against a
**real Parse.bot connector scraping live PropertyGuru Singapore listings** (not a stub — it was a
`raise NotImplementedError` stub before this build; it's now a working connector with 6 real
endpoints). `app/bootstrap.py` syncs a bounded catalog (`PARSE_BOT_MAX_SEARCH_PAGES`,
`PARSE_BOT_DETAIL_ENRICH_LIMIT`) into the normal `properties`/`agents`/`listing_agent_links`
tables at startup, same as the demo fixture path, so the rest of the system can't tell the
difference except via `source_mode: "live_authorized"`.

Two things worth knowing before touching this:
- **Parse.bot bills per call against a small daily quota** (100 requests/day on this plan). A
  TTL guard (`PARSE_BOT_SYNC_TTL_MINUTES`, default 1440 in `.env` right now) skips re-syncing
  while the cached catalog is still fresh, so `uvicorn --reload` restarts don't burn it — but
  running `scripts/sync_live_listings.py` or deleting the DB will. `provider.health()`
  deliberately never makes a live call either, for the same reason.
- PropertyGuru listing pages expose an agent's name and CEA license number but never a
  phone/email, so `get_listing_agent` honestly returns `approved_contact=None` for every live
  listing — `HandoffService` then safely falls back to the original-listing-only channel instead
  of a contact channel ever being fabricated.

## API contract

Base path: `/api`. Every error response is `{"error": {"code", "message", "request_id", "details"}}`.

| Method + path | Purpose |
|---|---|
| `POST /chat` | free-text message → profile patch (works with or without an LLM) |
| `PUT /preferences?session_id=...` | persist a buyer-corrected, validated profile |
| `POST /recommendations` | run the full pipeline → top-5-or-fewer ranked listings |
| `GET /properties/{listing_id}` | listing detail incl. valuation eligibility |
| `POST /compare` | 2–3 listings → side-by-side attributes + caveats |
| `POST /feedback` | pairwise choice → updated soft weights + rerank |
| `POST /finance/estimate` | mortgage estimate + stress scenarios |
| `POST /handoffs/preview` | safe contact choices for a listing (never exposes unverified contact) |
| `POST /handoffs` | execute a consented handoff; server derives `listing_id`→`agent_id` itself |
| `GET /health` | status, build SHA, architecture (`uname -m`), provider health |
| `GET /metrics` | request count, error count, p50/p95 latency |

Full request/response shapes: `app/schemas/*.py`, or just open `/docs` once the server is running.

## Connecting a frontend

1. Set `HOMERUN_CORS_ORIGINS` in `.env` to your dev server's origin (default already includes
   `http://localhost:5173` for Vite).
2. Call the API with `credentials: "omit"` (no cookies are used — session state is a
   `session_id` string you generate client-side on first load and pass in every request body).

```ts
const res = await fetch("http://localhost:8000/api/chat", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ session_id: sessionId, message: userMessage }),
});
const { session_id, buyer_profile, followup_question } = await res.json();
```

3. Every response carries an `X-Request-ID` header (also in the body for recommendations/handoffs)
   — surface it in a "system evidence panel" per PRD section 12.

## Configuration

Copy `.env.example` to `.env`. Key switches:

- `LISTING_PROVIDER=demo_fixture|authorized` — demo fixture is always available offline; the
  authorized Parse.bot/PropertyGuru connector (`app/providers/listing/authorized_provider.py`)
  is live and working once `PARSE_BOT_BASE_URL`/`PARSE_BOT_API_KEY` are set (see "Live listing
  data" above for the daily-quota caveat).
- `LLM_PROVIDER=template|gemini` — template is a fully deterministic, offline regex extractor and
  the fallback every other provider degrades to on error.
- `DIRECT_LEAD_SUBMISSION_ENABLED=false` — PRD section 16 open decision; default keeps the system
  on the original-listing contact route only until direct lead submission is explicitly authorized.

## Testing

```bash
pytest -q
```

Covers: hard-constraint filtering (price/bedroom/type/status), the handoff state machine +
acceptance tests (identity can't be swapped by the client, consent gating, missing-contact
fallback), mortgage math, the ML training/evaluation pipeline (beats baseline, reports interval
coverage, never scores condos), and the end-to-end chat → recommend → compare → feedback flow.

## Deployment to IBM Z / LinuxONE

See `scripts/bootstrap.sh` (provisions venv, verifies `uname -m`, installs pinned deps, runs a
package smoke test, bootstraps the DB + demo catalog, trains the valuation model, runs tests) and
`scripts/homerun-backend.service` (systemd unit). Put Nginx/Caddy with TLS in front for any
publicly exposed deployment per PRD section 9.

**Actually deployed and currently running** on an IBM LinuxONE Community Cloud VM
(`zdatathonhomerun`, Ubuntu 24.04, confirmed `uname -m` → `s390x`) as the `homerun-backend`
systemd unit — `curl http://148.100.77.89:8000/api/health` should return
`"architecture":"s390x"`. Notes for anyone redeploying this way:

- PyPI has no prebuilt `numpy`/`pandas`/`scikit-learn`/`scipy` wheels for s390x, so a plain
  `pip install -r requirements.txt` tries to compile them from source (numpy alone can run for
  a very long time). Install those four via `apt` instead (`ports.ubuntu.com` carries s390x
  builds) and create the venv with `python3 -m venv --system-site-packages .venv` so it inherits
  them; `pip install` the rest from a copy of `requirements.txt` with those four lines stripped
  (`pydantic`/`pydantic-core` does have a real manylinux s390x wheel on PyPI, so that one's fine
  as-is).
- No public port is open by default except SSH — `sudo iptables -I INPUT 2 -p tcp --dport 8000
  -m conntrack --ctstate NEW -j ACCEPT` (persisted via `netfilter-persistent save`) is what makes
  :8000 reachable; there's no TLS/auth in front, so treat this as a judging-window deployment,
  not a production one.
- If `data/homerun.db` is being copied over rather than synced fresh on the box, checkpoint WAL
  first (`sqlite3 data/homerun.db 'PRAGMA wal_checkpoint(FULL);'`) or copy the `-wal`/`-shm`
  sidecar files too — otherwise the freshly-copied DB can be missing the most recent commits,
  the TTL guard above sees a stale/empty `fetched_at` and triggers an unwanted live re-sync.
