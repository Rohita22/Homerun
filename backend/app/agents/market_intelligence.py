"""Agent 2 — Market Intelligence (PRD section 5).

Takes the ``BuyerProfile`` and the normalized inventory already cached in the database (synced
from the active ``ListingProvider``) and applies deterministic hard filters via
``HardFilterService``. Hard filters are never relaxed silently — excluded and
needs-confirmation listings are returned alongside the eligible candidate set so the API can
produce PRD section 4's "zero matches, ask which hard constraint user permits changing" flow.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.agents.base import timed_result
from app.domain.entities import AgentResult, BuyerProfile, PropertyListing
from app.services.ranking_service import HardFilterService


@dataclass
class CandidateSet:
    eligible: list[PropertyListing] = field(default_factory=list)
    excluded: list[dict] = field(default_factory=list)
    needs_confirmation: list[dict] = field(default_factory=list)
    source_mode: str = "demo_fixture"


class MarketIntelligenceAgent:
    name = "market_intelligence"

    def __init__(self, hard_filter_service: HardFilterService | None = None) -> None:
        self._hard_filter = hard_filter_service or HardFilterService()

    def run(
        self, request_id: str, profile: BuyerProfile, inventory: list[PropertyListing], source_mode: str
    ) -> AgentResult[CandidateSet]:
        def _work() -> CandidateSet:
            filtered = self._hard_filter.apply(inventory, profile)
            return CandidateSet(
                eligible=filtered.eligible,
                excluded=filtered.excluded,
                needs_confirmation=filtered.needs_confirmation,
                source_mode=source_mode,
            )

        return timed_result(self.name, request_id, _work)
