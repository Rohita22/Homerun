"""``POST /api/compare`` (PRD section 11)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_property_repository
from app.core.errors import ValidationFailedError
from app.repositories.property_repository import PropertyRepository
from app.schemas.property import CompareRequest, CompareResponse, PropertyOut
from app.services.compare_service import CompareService

router = APIRouter(tags=["compare"])


@router.post("/compare", response_model=CompareResponse)
def post_compare(
    body: CompareRequest,
    property_repo: PropertyRepository = Depends(get_property_repository),
) -> CompareResponse:
    if not 2 <= len(body.listing_ids) <= 3:
        raise ValidationFailedError("Compare accepts between 2 and 3 listing_ids.")

    listings = property_repo.get_by_ids(body.listing_ids)
    if len(listings) != len(body.listing_ids):
        found = {listing_.listing_id for listing_ in listings}
        missing = [lid for lid in body.listing_ids if lid not in found]
        raise ValidationFailedError(f"Unknown listing_id(s): {missing}")

    differences, caveats = CompareService().build(listings)
    return CompareResponse(
        listings=[PropertyOut.from_entity(listing_) for listing_ in listings],
        differences=differences,
        caveats=caveats,
    )
