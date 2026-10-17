"""Central application configuration.

Single source of truth for environment-driven settings (12-factor style). Everything else in
the codebase reads configuration through this module instead of calling ``os.environ`` directly,
so behavior stays testable and swappable (Dependency Inversion: callers depend on ``Settings``,
not on the environment).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Core ---
    homerun_env: str = "development"
    homerun_debug: bool = True
    homerun_secret_key: str = "change-me-in-production"
    homerun_build_sha: str = "dev"

    # --- Database ---
    homerun_database_url: str = f"sqlite:///{(BACKEND_ROOT / 'data' / 'homerun.db').as_posix()}"

    # --- Listing provider (Dependency Inversion: orchestrator only knows the interface) ---
    listing_provider: str = "scraped"  # always the PropertyGuru scraper; see factory.py
    parse_bot_base_url: str | None = None
    parse_bot_api_key: str | None = None
    # Bounded so a live sync has a predictable worst-case latency instead of scraping the whole
    # marketplace on every bootstrap (PRD section 6: "Cache with TTL and provenance").
    parse_bot_max_search_pages: int = 2
    parse_bot_include_rent: bool = True
    parse_bot_detail_enrich_limit: int = 20
    # Parse.bot bills per call with a daily quota; skip re-syncing on every bootstrap (e.g. every
    # `--reload` restart in dev) while the cached catalog is still within this TTL.
    parse_bot_sync_ttl_minutes: int = 30

    # --- Playwright PropertyGuru scraper (LISTING_PROVIDER=scraped) ---
    # Runs inside the API process on a timer (and via ``python -m app.scraper``); results land in
    # the same ``properties`` table the rest of the app already reads.
    scrape_enabled: bool = True
    scrape_interval_hours: float = 1.0
    # Hourly runs are "quick": only the first N pages of each target (where new / re-priced listings
    # surface) and unchanged listings are just touched, not rewritten. Every ``scrape_full_every_hours``
    # a full crawl runs, which is also the only run allowed to retire listings that went missing.
    scrape_quick_pages: int = 5
    scrape_full_every_hours: float = 12.0
    # Comma separated ``<propertyguru path>:<max pages>`` pairs, 20 listings per page.
    scrape_targets: str = "hdb-for-sale:30,condo-for-sale:20"
    scrape_delay_seconds: float = 8.0  # polite pause between page loads (+ random jitter)
    scrape_headless: bool = True
    scrape_max_retries: int = 3
    # A listing not re-seen for this long is marked inactive (it fell out of the crawl window or
    # was taken down). Kept well above the interval so one failed run never wipes the catalog.
    scrape_stale_after_hours: float = 72.0
    # Towns offered as chips on the profile screen (the design shows five).
    ui_towns: str = "Bishan,Tampines,Queenstown,Jurong West,Punggol"
    # Shared secret for POST /api/admin/ingest (scraped listings pushed from a machine that can run
    # Chromium, since IBM Z / s390x has no Playwright browser build). Empty = ingest disabled.
    admin_token: str = ""
    # Built Homerun UI served at "/" (frontend/app/dist). Missing dir = API only.
    frontend_dir: str = str(BACKEND_ROOT.parent / "frontend" / "app" / "dist")
    # Optional OneMap API token (free account) lifts the geocoder's anonymous rate limit.
    onemap_token: str | None = None

    # --- LLM provider ---
    llm_provider: str = "template"  # "template" | "gemini" | "groq"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.1-pro-preview"
    # Used when the primary model is unknown to / has no quota on this API key.
    gemini_fallback_model: str = "gemini-3.8-flash"
    groq_api_key: str | None = None

    # --- Voice AI (Gemini Live API, proxied through /api/voice/ws so the key stays server-side) ---
    gemini_live_model: str = "gemini-3.8-live"
    gemini_live_fallback_model: str = "gemini-3.1-flash-live-preview"
    gemini_live_voice: str = "Puck"

    # --- Session / retention (PRD section 9: Security and privacy) ---
    session_ttl_hours: int = 24

    # --- CORS ---
    homerun_cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # --- Handoff policy (PRD section 16 open decision: "Decide whether direct lead submission
    # is authorized. Default: original listing contact link.") ---
    direct_lead_submission_enabled: bool = False

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.homerun_cors_origins.split(",") if origin.strip()]

    @property
    def gemini_model_chain(self) -> list[str]:
        return [self.gemini_model, self.gemini_fallback_model]

    @property
    def ui_town_list(self) -> list[str]:
        return [t.strip() for t in self.ui_towns.split(",") if t.strip()]

    @property
    def scrape_target_list(self) -> list[tuple[str, int]]:
        targets: list[tuple[str, int]] = []
        for part in self.scrape_targets.split(","):
            part = part.strip()
            if not part:
                continue
            path, _, pages = part.partition(":")
            targets.append((path.strip("/ "), int(pages) if pages.strip() else 1))
        return targets

    @property
    def is_sqlite(self) -> bool:
        return self.homerun_database_url.startswith("sqlite")

    @property
    def fixtures_dir(self) -> Path:
        return BACKEND_ROOT / "app" / "fixtures"

    @property
    def ml_artifacts_dir(self) -> Path:
        path = BACKEND_ROOT / "app" / "ml" / "artifacts"
        path.mkdir(parents=True, exist_ok=True)
        return path


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton; tests can call ``get_settings.cache_clear()`` to reload."""
    return Settings()
