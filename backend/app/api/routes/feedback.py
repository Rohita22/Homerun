"""``POST /api/feedback`` (PRD section 11 / 7D): pairwise preference learning. Updates the
buyer's soft weights, persists the feedback event, and reranks — hard constraints are never
touched here, matching the PRD QA case: "Buyer chooses a pairwise preference: reranking updates
and constraint filter remains intact."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import (
    get_feedback_repository,
    get_orchestrator,
    get_property_repository,
    get_request_id,
    get_session_repository,
)
from app.api.routes.recommendations import _to_item_out
from app.core.errors import NotFoundError, ValidationFailedError
from app.domain.enums import FeedbackEventType
from app.orchestration.orchestrator import RecommendationOrchestrator
from app.repositories.feedback_repository import FeedbackRepository
from app.repositories.property_repository import PropertyRepository
from app.repositories.session_repository import SessionRepository
from app.schemas.common import AgentTraceOut
from app.schemas.recommendation import FeedbackRequest, FeedbackResponse
from app.services.preference_learning import update_weights
from app.services.ranking_service import MultiObjectiveRanker

router = APIRouter(tags=["feedback"])


@router.post("/feedback", response_model=FeedbackResponse)
def post_feedback(
    body: FeedbackRequest,
    request_id: str = Depends(get_request_id),
    session_repo: SessionRepository = Depends(get_session_repository),
    feedback_repo: FeedbackRepository = Depends(get_feedback_repository),
    property_repo: PropertyRepository = Depends(get_property_repository),
    orchestrator: RecommendationOrchestrator = Depends(get_orchestrator),
) -> FeedbackResponse:
    profile = session_repo.get_profile(body.session_id)
    if profile is None:
        raise ValidationFailedError("No buyer profile found for this session.")

    chosen_listing = property_repo.get(body.chosen_id)
    if chosen_listing is None:
        raise NotFoundError(f"Listing {body.chosen_id} not found.")

    current_weights = dict(profile.soft_weights)
    updated_weights = current_weights

    if body.rejected_id and body.event_type == FeedbackEventType.PAIRWISE_CHOICE.value:
        rejected_listing = property_repo.get(body.rejected_id)
        if rejected_listing is None:
            raise NotFoundError(f"Listing {body.rejected_id} not found.")

        eligible = [chosen_listing, rejected_listing]
        ranked = MultiObjectiveRanker().rank(eligible, profile, weights=current_weights, limit=2)
        factors_by_id = {item.listing_id: item.factors for item in ranked}
        updated_weights = update_weights(
            current_weights,
            chosen_factors=factors_by_id.get(body.chosen_id, {}),
            rejected_factors=factors_by_id.get(body.rejected_id, {}),
        )

    feedback_repo.record(
        session_id=body.session_id,
        event_type=body.event_type,
        preferred_listing_id=body.chosen_id,
        rejected_listing_id=body.rejected_id,
    )
    profile = session_repo.merge_patch(body.session_id, {"soft_weights": updated_weights})

    result = orchestrator.produce_recommendations(request_id, profile, weights=updated_weights)
    items = [_to_item_out(item, property_repo) for item in result.ranked_items]

    return FeedbackResponse(
        updated_weights=updated_weights,
        new_run_id=result.run_id,
        items=items,
        trace=[AgentTraceOut.from_agent_result(r) for r in result.trace],
    )
