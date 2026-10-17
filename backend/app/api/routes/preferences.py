"""``PUT /api/preferences`` (PRD section 11): persist a buyer-corrected, validated profile from
the preference-review screen (PRD section 4)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_session_repository
from app.domain.entities import BuyerProfile
from app.repositories.session_repository import SessionRepository
from app.schemas.buyer import BuyerProfileIn, BuyerProfileOut

router = APIRouter(tags=["preferences"])


@router.put("/preferences", response_model=BuyerProfileOut)
def put_preferences(
    session_id: str,
    body: BuyerProfileIn,
    session_repo: SessionRepository = Depends(get_session_repository),
) -> BuyerProfileOut:
    session_repo.get_or_create(session_id)
    profile = BuyerProfile(session_id=session_id, **body.model_dump())
    saved = session_repo.save_profile(profile)
    return BuyerProfileOut(session_id=session_id, **saved.model_dump(exclude={"session_id", "updated_at"}))
