# Homerun frontend

Minimal React + TypeScript + Vite client for manually testing the [Homerun backend](../backend).
Not a polished production UI — it exists to click through the real PRD flow (chat → preferences
→ results → detail/compare → agent handoff) against a live API instead of using `/docs`.

## Run it

Requires the backend running first (see `../backend/README.md`), then:

```bash
npm install
npm run dev
```

Open http://localhost:5173. `.env` already points `VITE_API_BASE_URL` at
`http://localhost:8000/api`; change it if your backend runs elsewhere, and make sure
`HOMERUN_CORS_ORIGINS` in the backend's `.env` includes this origin (it does by default).

## Structure

```
src/
  api/client.ts     one typed function per backend endpoint — the only module that knows URLs
  api/types.ts      TS mirrors of backend/app/schemas/*.py
  lib/session.ts    client-side session_id persistence (localStorage, not cookies)
  components/       one component per PRD section 4 screen (Chat, PreferenceReview, Results,
                     PropertyDetail, Compare, Handoff) + EvidencePanel (health/trace sidebar)
  App.tsx           screen state machine wiring the flow together
```

## What to try

1. **Chat** — paste or type a message like the PRD's example buyer session; preferences get
   extracted without any LLM key configured (the backend's deterministic fallback).
2. **Preferences** — edit/confirm hard constraints, save & search.
3. **Results** — five ranked demo listings with HDB valuation estimates and reasons. Select two
   cards to send pairwise feedback and watch the ranking update; select 2–3 to compare.
4. **Property detail** — estimate a mortgage payment, then click "I'm interested".
5. **Handoff** — preview shows only safe contact choices for that listing's actual verified
   state (`fixture-104` is deliberately unverified, `fixture-105` has no agent, `fixture-108` is
   inactive — try those IDs via `/docs` on the backend to see every branch).

The sidebar always shows the backend's health, architecture, and the last request's trace ID —
useful for confirming you're actually talking to the live API.
