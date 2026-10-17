"""``POST /api/recommendations`` (PRD section 11): runs the full retrieve -> filter -> value ->
rank pipeline through :class:`RecommendationOrchestrator` and returns the top five (or fewer,
truthfully, per PRD section 4: "if fewer than 5, show true count")."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import (
    get_orchestrator,
    get_property_repository,
    get_request_id,
    get_session_repository,
    get_source_mode,
)
from app.core.errors import ValidationFailedError
from app.domain.entities import BuyerProfile
from app.orchestration.orchestrator import RecommendationOrchestrator
from app.repositories.property_repository import PropertyRepository
from app.repositories.session_repository import SessionRepository
from app.schemas.common import AgentTraceOut
from app.schemas.recommendation import (
    RecommendationItemOut,
    RecommendationRequest,
    RecommendationResponse,
    ValuationOut,
)

router = APIRouter(tags=["recommendations"])


def _to_item_out(item, property_repo) -> RecommendationItemOut:  # noqa: ANN001
    listing = property_repo.get(item.listing_id)
    return RecommendationItemOut(
        listing_id=item.listing_id,
        rank=item.rank,
        score=item.score,
        reasons=item.reasons,
        factors=item.factors,
        valuation_status=item.valuation_status,
        valuation=ValuationOut(**item.valuation.model_dump()) if item.valuation else None,
        address_public=listing.address_public if listing else None,
        asking_price_sgd=listing.asking_price_sgd if listing else None,
        town=listing.town if listing else None,
    )


@router.post("/recommendations", response_model=RecommendationResponse)
def post_recommendations(
    body: RecommendationRequest,
    request_id: str = Depends(get_request_id),
    orchestrator: RecommendationOrchestrator = Depends(get_orchestrator),
    session_repo: SessionRepository = Depends(get_session_repository),
    property_repo: PropertyRepository = Depends(get_property_repository),
    source_mode: str = Depends(get_source_mode),
) -> RecommendationResponse:
    session_repo.get_or_create(body.session_id)

    if body.profile is not None:
        profile = BuyerProfile(session_id=body.session_id, **body.profile.model_dump())
        session_repo.save_profile(profile)
    else:
        profile = session_repo.get_profile(body.session_id)

    if profile is None:
        raise ValidationFailedError(
            "No buyer profile found for this session; submit preferences first."
        )

    result = orchestrator.produce_recommendations(request_id, profile, limit=body.limit)

    warnings = list(result.warnings)
    if source_mode == "demo_fixture":
        warnings.append("Inventory is demonstration data, not live availability.")
    if not result.ranked_items:
        warnings.append(
            "No matched inventory for your current hard constraints. Consider relaxing one, "
            "e.g. budget or town."
        )

    items = [_to_item_out(item, property_repo) for item in result.ranked_items]

    return RecommendationResponse(
        run_id=result.run_id,
        session_id=body.session_id,
        source_mode=source_mode,
        requested_count=body.limit,
        returned_count=len(items),
        items=items,
        excluded_count=len(result.candidate_set.excluded),
        needs_confirmation_count=len(result.candidate_set.needs_confirmation),
        warnings=warnings,
        trace=[AgentTraceOut.from_agent_result(r) for r in result.trace],
    )
