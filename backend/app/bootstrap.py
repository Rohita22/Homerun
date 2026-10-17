"""Startup bootstrap: creates tables and syncs the active ``ListingProvider``'s catalog into the
normalized ``properties``/``agents``/``listing_agent_links`` tables that the rest of the app
reads through :class:`PropertyRepository` (PRD section 6: "Cache with TTL and provenance").

:class:`DemoFixtureProvider` is synced eagerly (small, static, offline-safe catalog).
:class:`AuthorizedListingProvider`, once enabled, is synced eagerly too via ``sync_catalog()`` —
a bounded, logged pull of genuinely live PropertyGuru inventory (not a schedule/webhook yet;
re-run ``python -m app.bootstrap`` or ``scripts/sync_live_listings.py`` to refresh it, which is
the "TTL" half of the PRD requirement until a background refresh job exists).
"""

from __future__ import annotations

from datetime import timedelta

from app.core.config import get_settings
from app.core.errors import ProviderUnavailableError
from app.core.logging import get_logger
from app.core.time import utcnow
from app.db.base import SessionLocal, init_db
from app.providers.listing.authorized_provider import AuthorizedListingProvider
from app.providers.listing.demo_fixture_provider import DemoFixtureProvider
from app.providers.listing.factory import get_listing_provider
from app.providers.listing.scraped_provider import ScrapedListingProvider
from app.repositories.property_repository import PropertyRepository

logger = get_logger(__name__)


def bootstrap() -> None:
    init_db()
    provider = get_listing_provider()
    db = SessionLocal()
    try:
        repo = PropertyRepository(db)
        if isinstance(provider, AuthorizedListingProvider):
            ttl_minutes = get_settings().parse_bot_sync_ttl_minutes
            last_fetched = repo.latest_fetched_at(provider="authorized_parse_bot")
            if last_fetched and utcnow() - last_fetched < timedelta(minutes=ttl_minutes):
                logger.info(
                    "bootstrap_live_sync_skipped reason=cache_still_fresh last_fetched_at=%s "
                    "ttl_minutes=%d",
                    last_fetched, ttl_minutes,
                )
                return
        if isinstance(provider, DemoFixtureProvider):
            repo.upsert_many(provider.all_listings())
            for agent in provider.all_agents():
                repo.upsert_agent(agent)
            for link in provider.all_links():
                repo.upsert_link(link)
            db.commit()
            logger.info(
                "bootstrap_complete provider=%s listings=%d agents=%d links=%d",
                provider.name,
                len(provider.all_listings()),
                len(provider.all_agents()),
                len(provider.all_links()),
            )
        elif isinstance(provider, AuthorizedListingProvider):
            try:
                listings, agents, links = provider.sync_catalog()
            except ProviderUnavailableError as exc:
                logger.warning(
                    "bootstrap_live_sync_unavailable provider=%s error=%s", provider.name, exc
                )
                return
            repo.upsert_many(listings)
            for agent in agents:
                repo.upsert_agent(agent)
            for link in links:
                repo.upsert_link(link)
            db.commit()
            logger.info(
                "bootstrap_complete provider=%s source=live_authorized listings=%d agents=%d "
                "links=%d",
                provider.name, len(listings), len(agents), len(links),
            )
        elif isinstance(provider, ScrapedListingProvider):
            # Nothing to sync here: the scraper scheduler (app.scraper.scheduler, started in
            # main.py's lifespan) fills ``properties`` on its own 12h timer.
            logger.info("bootstrap_scraped_provider catalog_size=%d", repo.count("propertyguru_scraper"))
        else:
            logger.warning(
                "bootstrap_skipped_sync provider=%s reason=unknown_provider_type", provider.name
            )
    finally:
        db.close()


if __name__ == "__main__":
    from app.core.logging import configure_logging

    configure_logging()
    bootstrap()
