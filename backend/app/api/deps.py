"""FastAPI dependency wiring — the composition root.

This is the one module allowed to know about every concrete class; every route handler asks for
a pre-wired service via ``Depends(...)`` and never constructs a repository, agent or provider
itself (Dependency Inversion applied at the framework boundary). Swapping any implementation —
a different listing provider, a trained valuation model, a different DB — only ever touches this
file plus its matching factory module.
"""

from __future__ import annotations

from collections.abc import Generator

from fastapi import Depends, Request
from sqlalchemy.orm import Session as DbSession

from app.agents.affordability_agent import AffordabilityRiskAgent
from app.agents.buyer_intelligence import BuyerIntelligenceAgent
from app.agents.market_intelligence import MarketIntelligenceAgent
from app.agents.matching_decision_agent import MatchingDecisionAgent
from app.agents.valuation_agent import ValuationAgent
from app.core.config import Settings, get_settings
from app.db.base import get_db
from app.domain.enums import SourceMode
from app.ml.valuation_service import get_valuation_service
from app.orchestration.orchestrator import RecommendationOrchestrator
from app.providers.llm.factory import get_llm_provider
from app.providers.listing.factory import get_listing_provider
from app.repositories.audit_repository import AuditRepository
from app.repositories.feedback_repository import FeedbackRepository
from app.repositories.handoff_repository import HandoffRepository
from app.repositories.property_repository import PropertyRepository
from app.repositories.recommendation_repository import RecommendationRepository
from app.repositories.session_repository import SessionRepository
from app.services.consent_service import ConsentService
from app.services.finance_service import FinanceCalculator
from app.services.handoff_service import HandoffService
from app.services.ranking_service import HardFilterService, MultiObjectiveRanker


def get_request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "req-unknown")


def get_app_settings() -> Settings:
    return get_settings()


# --- Repositories (per-request, bound to the request's DB session) ---


def get_property_repository(db: DbSession = Depends(get_db)) -> PropertyRepository:
    return PropertyRepository(db)


def get_session_repository(db: DbSession = Depends(get_db)) -> SessionRepository:
    return SessionRepository(db)


def get_recommendation_repository(db: DbSession = Depends(get_db)) -> RecommendationRepository:
    return RecommendationRepository(db)


def get_feedback_repository(db: DbSession = Depends(get_db)) -> FeedbackRepository:
    return FeedbackRepository(db)


def get_handoff_repository(db: DbSession = Depends(get_db)) -> HandoffRepository:
    return HandoffRepository(db)


def get_audit_repository(db: DbSession = Depends(get_db)) -> AuditRepository:
    return AuditRepository(db)


# --- Stateless agents/services ---


def get_buyer_intelligence_agent() -> BuyerIntelligenceAgent:
    return BuyerIntelligenceAgent(get_llm_provider())


def get_market_intelligence_agent() -> MarketIntelligenceAgent:
    return MarketIntelligenceAgent(HardFilterService())


def get_valuation_agent() -> ValuationAgent:
    return ValuationAgent(get_valuation_service())


def get_affordability_agent() -> AffordabilityRiskAgent:
    return AffordabilityRiskAgent(FinanceCalculator())


def get_matching_decision_agent() -> MatchingDecisionAgent:
    return MatchingDecisionAgent(MultiObjectiveRanker())


def get_consent_service(settings: Settings = Depends(get_app_settings)) -> ConsentService:
    return ConsentService(direct_lead_submission_enabled=settings.direct_lead_submission_enabled)


def get_handoff_service(
    repo: HandoffRepository = Depends(get_handoff_repository),
    consent_service: ConsentService = Depends(get_consent_service),
) -> HandoffService:
    return HandoffService(repo, consent_service)


def get_source_mode(settings: Settings = Depends(get_app_settings)) -> str:
    return (
        SourceMode.LIVE_AUTHORIZED.value
        if settings.listing_provider == "authorized"
        else SourceMode.DEMO_FIXTURE.value
    )


def get_orchestrator(
    property_repo: PropertyRepository = Depends(get_property_repository),
    recommendation_repo: RecommendationRepository = Depends(get_recommendation_repository),
    market_agent: MarketIntelligenceAgent = Depends(get_market_intelligence_agent),
    valuation_agent: ValuationAgent = Depends(get_valuation_agent),
    matching_agent: MatchingDecisionAgent = Depends(get_matching_decision_agent),
    source_mode: str = Depends(get_source_mode),
) -> RecommendationOrchestrator:
    return RecommendationOrchestrator(
        property_repo=property_repo,
        recommendation_repo=recommendation_repo,
        market_agent=market_agent,
        valuation_agent=valuation_agent,
        matching_agent=matching_agent,
        source_mode=source_mode,
    )
