"""Listing provider backed by the PropertyGuru scraper's own database rows.

Unlike ``AuthorizedListingProvider`` this never calls the network: the scheduler
(``app.scraper.scheduler``) keeps the ``properties`` table fresh and this provider simply reads it,
so a buyer request is never slowed down or blocked by a scrape.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from app.core.config import get_settings
from app.core.time import utcnow
from app.db.base import SessionLocal
from app.domain.entities import Agent, ListingAgentLink, PropertyListing
from app.repositories.property_repository import PropertyRepository
from app.scraper.parser import PROVIDER
from app.scraper.service import last_successful_run

DB_PROVIDER_NAME = PROVIDER


class ScrapedListingProvider:
    name = "scraped"

    def search_listings(
        self, filters: dict[str, Any], page: int = 1, page_size: int = 50
    ) -> list[PropertyListing]:
        db = SessionLocal()
        try:
            listings = [
                L for L in PropertyRepository(db).list_all(DB_PROVIDER_NAME) if L.status == "active"
            ]
        finally:
            db.close()
        wanted = filters.get("transaction_type")
        if wanted:
            listings = [L for L in listings if getattr(L.transaction_type, "value", L.transaction_type) == wanted]
        start = (page - 1) * page_size
        return listings[start : start + page_size]

    def get_listing(self, source_listing_id: str) -> PropertyListing | None:
        db = SessionLocal()
        try:
            return PropertyRepository(db).get(source_listing_id)
        finally:
            db.close()

    def get_listing_agent(self, source_listing_id: str) -> tuple[Agent, ListingAgentLink] | None:
        db = SessionLocal()
        try:
            return PropertyRepository(db).get_agent_link(source_listing_id)
        finally:
            db.close()

    def health(self) -> bool:
        """Healthy = a scrape succeeded recently enough (two intervals) to trust the catalog."""
        db = SessionLocal()
        try:
            run = last_successful_run(db)
        finally:
            db.close()
        if run is None or run.finished_at is None:
            return False
        max_age = timedelta(hours=get_settings().scrape_interval_hours * 2)
        return utcnow() - run.finished_at < max_age
