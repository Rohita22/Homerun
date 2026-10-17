"""Always-available, licensed/synthetic local listing fixture (PRD product principle: "Ensure
the entire demo remains operable from a licensed or synthetic local listing fixture if
third-party integration fails"). Implements the same ``ListingProvider`` interface as any future
authorized connector, so the rest of the system cannot tell the difference except via
``source_mode`` warnings surfaced to the UI.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.time import utcnow
from app.domain.entities import Agent, ListingAgentLink, PropertyListing
from app.domain.enums import AssociationStatus


class DemoFixtureProvider:
    name = "demo_fixture"

    def __init__(self, fixtures_dir: Path) -> None:
        self._fixtures_dir = fixtures_dir
        self._listings: dict[str, PropertyListing] = {}
        self._agents: dict[str, Agent] = {}
        self._links: dict[str, ListingAgentLink] = {}
        self._load()

    def _load(self) -> None:
        listings_raw = json.loads((self._fixtures_dir / "demo_listings.json").read_text())
        agents_raw = json.loads((self._fixtures_dir / "demo_agents.json").read_text())
        links_raw = json.loads((self._fixtures_dir / "demo_listing_agent_links.json").read_text())

        now = utcnow()
        for raw in listings_raw:
            listing = PropertyListing.model_validate({**raw, "fetched_at": now})
            self._listings[listing.listing_id] = listing

        for raw in agents_raw:
            agent = Agent.model_validate(raw)
            self._agents[agent.agent_id] = agent

        for raw in links_raw:
            link = ListingAgentLink.model_validate(
                {
                    **raw,
                    "association_status": AssociationStatus(raw["association_status"]),
                    "checked_at": now,
                }
            )
            self._links[link.listing_id] = link

    def search_listings(
        self, filters: dict[str, Any], page: int = 1, page_size: int = 50
    ) -> list[PropertyListing]:
        results = list(self._listings.values())
        page_size = max(1, page_size)
        start = max(0, (page - 1) * page_size)
        return results[start : start + page_size]

    def get_listing(self, source_listing_id: str) -> PropertyListing | None:
        return self._listings.get(source_listing_id)

    def get_listing_agent(self, source_listing_id: str) -> tuple[Agent, ListingAgentLink] | None:
        link = self._links.get(source_listing_id)
        if link is None:
            return None
        agent = self._agents.get(link.agent_id)
        if agent is None:
            return None
        return agent, link

    def health(self) -> bool:
        return True

    def all_listings(self) -> list[PropertyListing]:
        return list(self._listings.values())

    def all_agents(self) -> list[Agent]:
        return list(self._agents.values())

    def all_links(self) -> list[ListingAgentLink]:
        return list(self._links.values())
