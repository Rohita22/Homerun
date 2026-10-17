"""Agent 5 — Matching & Decision (PRD section 5). Produces the Pareto-aware, diversified top
five from the eligible candidate set plus per-item utility breakdown and rationale, via
``MultiObjectiveRanker``. Valuation is attached per item but — per PRD section 7B — is never
used as a ranking objective for unsupported property types."""

from __future__ import annotations

from app.agents.base import timed_result
from app.domain.entities import AgentResult, BuyerProfile, PropertyListing, RankedItem, ValuationResult
from app.services.ranking_service import MultiObjectiveRanker


class MatchingDecisionAgent:
    name = "matching_decision"
    version = "multiobjective-ranker-v1"

    def __init__(self, ranker: MultiObjectiveRanker | None = None) -> None:
        self._ranker = ranker or MultiObjectiveRanker()

    def run(
        self,
        request_id: str,
        profile: BuyerProfile,
        eligible_listings: list[PropertyListing],
        weights: dict[str, float] | None = None,
        valuations: dict[str, ValuationResult] | None = None,
        limit: int = 5,
    ) -> AgentResult[list[RankedItem]]:
        def _work() -> list[RankedItem]:
            ranked = self._ranker.rank(eligible_listings, profile, weights=weights, limit=limit)
            if valuations:
                for item in ranked:
                    valuation = valuations.get(item.listing_id)
                    if valuation is not None:
                        item.valuation = valuation
                        item.valuation_status = valuation.status
            return ranked

        return timed_result(self.name, request_id, _work, model_version=self.version)
