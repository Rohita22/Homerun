"""``POST /api/admin/ingest`` — accept scraped listings pushed from another machine.

IBM Z (s390x) has no Playwright/Chromium build, so the scraper runs where a browser exists
(``python -m app.scraper --push``) and ships the normalized rows here. Protected by a shared
secret (``ADMIN_TOKEN``); with no secret configured the endpoint is disabled.
"""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DbSession

from app.core.config import Settings
from app.core.errors import ProviderUnavailableError, UnauthorizedChannelError
from app.core.logging import get_logger
from app.core.time import utcnow
from app.api.deps import get_app_settings
from app.db.base import get_db
from app.db.models import ScrapeRunRow
from app.domain.entities import Agent, ListingAgentLink, PropertyListing
from app.repositories.property_repository import PropertyRepository
from app.scraper.parser import PROVIDER

logger = get_logger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])


class IngestBatch(BaseModel):
    listings: list[PropertyListing]
    agents: list[Agent] = Field(default_factory=list)
    links: list[ListingAgentLink] = Field(default_factory=list)
    deactivate_missing: bool = True  # this push is the full current catalog


@router.post("/ingest")
def ingest(
    batch: IngestBatch,
    x_admin_token: str = Header(default=""),
    settings: Settings = Depends(get_app_settings),
    db: DbSession = Depends(get_db),
) -> dict:
    if not settings.admin_token:
        raise ProviderUnavailableError("Ingest is disabled: set ADMIN_TOKEN on the server.")
    if not hmac.compare_digest(x_admin_token, settings.admin_token):
        raise UnauthorizedChannelError("Invalid admin token.")
    foreign = [l.listing_id for l in batch.listings if l.provider != PROVIDER]
    if foreign:
        raise UnauthorizedChannelError(f"Only {PROVIDER} listings may be ingested.")

    started = utcnow()
    repo = PropertyRepository(db)
    for listing in batch.listings:
        repo.upsert(listing)
    db.flush()
    for agent in batch.agents:
        repo.upsert_agent(agent)
    db.flush()
    for link in batch.links:
        repo.replace_link(link)

    deactivated = 0
    if batch.deactivate_missing and batch.listings:
        keep = {l.listing_id for l in batch.listings}
        for existing in repo.list_all(PROVIDER, status="active"):
            if existing.listing_id not in keep:
                repo.mark_inactive(existing.listing_id)
                deactivated += 1
    db.add(
        ScrapeRunRow(
            started_at=started, finished_at=utcnow(), status="ok", pages_ok=0, pages_failed=0,
            listings_seen=len(batch.listings), listings_deactivated=deactivated,
            detail_json={"source": "push"},
        )
    )
    db.commit()
    logger.info("ingest_complete listings=%d deactivated=%d", len(batch.listings), deactivated)
    return {"ingested": len(batch.listings), "deactivated": deactivated}
