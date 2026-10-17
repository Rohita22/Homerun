"""Central orchestration state machine (PRD section 5):

    extract -> validate -> retrieve -> enrich -> value (if eligible) -> calculate financing
    (if sufficient inputs) -> rank -> explain

``extract`` happens in the chat endpoint via ``BuyerIntelligenceAgent`` before a profile exists,
so this orchestrator starts from ``validate`` (a parsed, persisted ``BuyerProfile``). Financing
depends on buyer-supplied loan terms that are not part of a ranking request, so it is exposed as
its own endpoint/agent call (PRD section 11: ``POST /api/finance/estimate``) rather than forced
into every recommendation run — this still satisfies "if sufficient inputs" by making the step
conditional on those inputs being present at all.

"On feedback, only necessary stages rerun": :meth:`rerank` re-enters at the rank stage using a
freshly re-fetched (cheap, in-memory) candidate set rather than re-running Buyer Intelligence.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field

from app.agents.market_intelligence import CandidateSet, MarketIntelligenceAgent
from app.agents.matching_decision_agent import MatchingDecisionAgent
from app.agents.valuation_agent import ValuationAgent
from app.core.logging import get_logger
from app.domain.entities import AgentResult, BuyerProfile, PropertyListing, RankedItem, ValuationResult
from app.domain.enums import AgentResultStatus, PropertyType
from app.repositories.property_repository import PropertyRepository
from app.repositories.recommendation_repository import RecommendationRepository

logger = get_logger(__name__)


@dataclass
class OrchestrationResult:
    run_id: str
    candidate_set: CandidateSet
    ranked_items: list[RankedItem]
    warnings: list[str] = field(default_factory=list)
    model_version: str = ""
    trace: list[AgentResult] = field(default_factory=list)


def _input_hash(profile: BuyerProfile, weights: dict[str, float]) -> str:
    payload = json.dumps(
        {"profile": profile.model_dump(mode="json"), "weights": weights}, sort_keys=True
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _aggregate_valuation_trace(request_id: str, runs: list[AgentResult]) -> AgentResult:
    """The valuation agent runs once per HDB-eligible listing; summarize all of them into a
    single trace row (status/timing/model-version/evidence) instead of flooding the UI's
    orchestration view with one row per listing."""
    if not runs:
        return AgentResult(
            request_id=request_id, agent_name="valuation", status=AgentResultStatus.OK.value,
            elapsed_ms=0.0, evidence_refs=[],
            warnings=["No HDB-eligible candidates to value."],
        )
    total_elapsed = sum(r.elapsed_ms for r in runs)
    model_version = next((r.model_version for r in runs if r.model_version), None)
    any_error = any(r.status == AgentResultStatus.ERROR.value for r in runs)
    warnings = [w for r in runs for w in r.warnings]
    return AgentResult(
        request_id=request_id,
        agent_name="valuation",
        status=AgentResultStatus.ERROR.value if any_error else AgentResultStatus.OK.value,
        elapsed_ms=round(total_elapsed, 3),
        model_version=model_version,
        warnings=warnings,
        evidence_refs=[f"valued {len(runs)} HDB candidate(s)"],
    )


class RecommendationOrchestrator:
    def __init__(
        self,
        property_repo: PropertyRepository,
        recommendation_repo: RecommendationRepository,
        market_agent: MarketIntelligenceAgent,
        valuation_agent: ValuationAgent,
        matching_agent: MatchingDecisionAgent,
        source_mode: str,
        inventory_provider: str | None = None,
    ) -> None:
        self._property_repo = property_repo
        self._recommendation_repo = recommendation_repo
        self._market_agent = market_agent
        self._valuation_agent = valuation_agent
        self._matching_agent = matching_agent
        self._source_mode = source_mode
        self._inventory_provider = inventory_provider

    def produce_recommendations(
        self,
        request_id: str,
        profile: BuyerProfile,
        limit: int = 5,
        weights: dict[str, float] | None = None,
        persist: bool = True,
        scope: Callable[[PropertyListing], bool] | None = None,
        value_ranked_only: bool = False,
    ) -> OrchestrationResult:
        warnings: list[str] = []
        trace: list[AgentResult] = []
        logger.info(
            "[ORCHESTRATOR] request_id=%s stage=START pipeline=extract->validate->retrieve->"
            "enrich->value->rank->explain session=%s",
            request_id, profile.session_id,
        )

        # --- retrieve ---
        inventory = self._property_repo.list_all(provider=self._inventory_provider)
        if scope is not None:
            inventory = [listing for listing in inventory if scope(listing)]
        logger.info(
            "[ORCHESTRATOR] request_id=%s stage=retrieve n_inventory=%d source_mode=%s",
            request_id, len(inventory), self._source_mode,
        )

        # --- enrich / hard-filter (Market Intelligence) ---
        market_result = self._market_agent.run(request_id, profile, inventory, self._source_mode)
        candidate_set = market_result.data or CandidateSet(source_mode=self._source_mode)
        warnings.extend(market_result.warnings)
        trace.append(market_result)
        logger.info(
            "[ORCHESTRATOR] request_id=%s stage=enrich agent=%s status=%s elapsed_ms=%.1f "
            "eligible=%d excluded=%d needs_confirmation=%d",
            request_id, market_result.agent_name, market_result.status, market_result.elapsed_ms,
            len(candidate_set.eligible), len(candidate_set.excluded), len(candidate_set.needs_confirmation),
        )

        if not candidate_set.eligible:
            run_id = (
                self._recommendation_repo.save_run(profile.session_id, "no-match", "n/a", [])
                if persist
                else "no-match"
            )
            logger.info(
                "[ORCHESTRATOR] request_id=%s stage=END outcome=no_eligible_candidates", request_id
            )
            return OrchestrationResult(
                run_id=run_id, candidate_set=candidate_set, ranked_items=[], warnings=warnings,
                trace=trace,
            )

        # --- value (HDB only; unsupported types are labeled, never scored on price) ---
        valuations: dict[str, ValuationResult] = {}
        valuation_runs: list[AgentResult] = []
        if not value_ranked_only:
            self._value_listings(request_id, candidate_set.eligible, valuations, valuation_runs)
            trace.append(_aggregate_valuation_trace(request_id, valuation_runs))

        # --- calculate financing: intentionally skipped here; see module docstring ---

        # --- rank ---
        decision_result = self._matching_agent.run(
            request_id, profile, candidate_set.eligible, weights=weights,
            valuations=valuations, limit=limit,
        )
        ranked_items = decision_result.data or []
        warnings.extend(decision_result.warnings)
        trace.append(decision_result)
        if value_ranked_only:
            # Valuation is never a ranking objective, so value only what is actually shown.
            by_id = {listing.listing_id: listing for listing in candidate_set.eligible}
            self._value_listings(
                request_id, [by_id[i.listing_id] for i in ranked_items], valuations, valuation_runs
            )
            trace.append(_aggregate_valuation_trace(request_id, valuation_runs))
            for item in ranked_items:
                found = valuations.get(item.listing_id)
                if found is not None:
                    item.valuation, item.valuation_status = found, found.status
        logger.info(
            "[ORCHESTRATOR] request_id=%s stage=rank agent=%s status=%s elapsed_ms=%.1f "
            "ranked_count=%d",
            request_id, decision_result.agent_name, decision_result.status,
            decision_result.elapsed_ms, len(ranked_items),
        )

        # --- explain: reasons/factors already attached per item by the ranker ---

        run_id = "ephemeral"
        if persist:
            run_id = self._recommendation_repo.save_run(
                profile.session_id,
                decision_result.model_version or "unknown",
                _input_hash(profile, weights or {}),
                ranked_items,
            )

        logger.info(
            "[ORCHESTRATOR] request_id=%s stage=END run_id=%s returned=%d", request_id, run_id,
            len(ranked_items),
        )
        return OrchestrationResult(
            run_id=run_id,
            candidate_set=candidate_set,
            ranked_items=ranked_items,
            warnings=warnings,
            model_version=decision_result.model_version or "",
            trace=trace,
        )

    def _value_listings(
        self,
        request_id: str,
        listings: list[PropertyListing],
        valuations: dict[str, ValuationResult],
        runs: list[AgentResult],
    ) -> None:
        for listing in listings:
            listing_type = getattr(listing.property_type, "value", listing.property_type)
            if listing_type != PropertyType.HDB.value:
                continue
            val_result = self._valuation_agent.run(request_id, listing)
            runs.append(val_result)
            if val_result.data:
                valuations[listing.listing_id] = val_result.data
        logger.info(
            "[ORCHESTRATOR] request_id=%s stage=value n_hdb_candidates=%d n_valued=%d "
            "total_elapsed_ms=%.1f",
            request_id, len(runs), len(valuations), sum(r.elapsed_ms for r in runs),
        )

    def rerank(
        self,
        request_id: str,
        profile: BuyerProfile,
        weights: dict[str, float],
        limit: int = 5,
    ) -> OrchestrationResult:
        """Feedback re-entry point: reuses retrieve + hard-filter but always recomputes rank
        with the updated weights (hard constraints are never relaxed by feedback)."""
        return self.produce_recommendations(request_id, profile, limit=limit, weights=weights)
