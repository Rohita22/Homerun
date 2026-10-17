"""Listing provider contract (PRD section 6: ``search_listings``, ``get_listing``,
``get_listing_agent``, ``health``).

Any concrete provider (demo fixture, future authorized Parse.bot/PropertyGuru connector) must
implement this ``Protocol``. Nothing outside ``app/providers`` imports a concrete provider class
directly — the orchestrator and agents depend only on this abstraction (Dependency Inversion +
Interface Segregation), and swapping providers is a config change (``LISTING_PROVIDER`` env var),
never a code change in callers (Open/Closed).
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from app.domain.entities import Agent, ListingAgentLink, PropertyListing


@runtime_checkable
class ListingProvider(Protocol):
    """Read-only access to a catalog of listings plus their agent association."""

    name: str

    def search_listings(
        self, filters: dict[str, Any], page: int = 1, page_size: int = 50
    ) -> list[PropertyListing]:
        """Return normalized listings matching ``filters``. Must never fabricate records."""
        ...

    def get_listing(self, source_listing_id: str) -> PropertyListing | None:
        ...

    def get_listing_agent(self, source_listing_id: str) -> tuple[Agent, ListingAgentLink] | None:
        """Return the agent + association evidence for a listing, or None if unknown."""
        ...

    def health(self) -> bool:
        ...
