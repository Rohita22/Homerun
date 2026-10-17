"""Ship the locally scraped catalog to a Homerun server (``POST /api/admin/ingest``).

IBM Z / LinuxONE (s390x) has no Playwright/Chromium build, so the server there cannot scrape.
Scrape where a browser exists, then push: this sends every active scraped listing (with its
geocode) plus the agents/links, and the server marks anything not in the push as inactive.
"""

from __future__ import annotations

import httpx
from sqlalchemy import select

from app.core.logging import get_logger
from app.db.base import SessionLocal
from app.db.models import AgentRow, ListingAgentLinkRow
from app.domain.entities import Agent, ListingAgentLink
from app.repositories.property_repository import PropertyRepository
from app.scraper.parser import PROVIDER

logger = get_logger(__name__)


def build_batch() -> dict:
    db = SessionLocal()
    try:
        repo = PropertyRepository(db)
        listings = repo.list_all(PROVIDER, status="active")
        ids = {l.listing_id for l in listings}
        links = [
            ListingAgentLink.model_validate(row)
            for row in db.execute(select(ListingAgentLinkRow)).scalars()
            if row.listing_id in ids
        ]
        agent_ids = {l.agent_id for l in links}
        agents = [
            Agent(
                agent_id=a.agent_id, provider_id=a.provider_id, name=a.name, cea_number=a.cea_number,
                approved_contact=a.approved_contact_json, verified_at=a.verified_at,
            )
            for a in db.execute(select(AgentRow)).scalars()
            if a.agent_id in agent_ids
        ]
    finally:
        db.close()
    return {
        "listings": [l.model_dump(mode="json") for l in listings],
        "agents": [a.model_dump(mode="json") for a in agents],
        "links": [l.model_dump(mode="json") for l in links],
        "deactivate_missing": True,
    }


def push_catalog(base_url: str, token: str, timeout_s: float = 120.0) -> dict:
    batch = build_batch()
    if not batch["listings"]:
        raise RuntimeError("nothing to push: no active scraped listings in the local database")
    response = httpx.post(
        base_url.rstrip("/") + "/api/admin/ingest",
        json=batch,
        headers={"X-Admin-Token": token},
        timeout=timeout_s,
    )
    response.raise_for_status()
    result = response.json()
    logger.info("push_complete url=%s %s", base_url, result)
    return result
