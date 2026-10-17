"""``GET /api/properties/{id}`` (PRD section 11 / section 4 property detail screen: "source
timestamp, missing fields and valuation eligibility")."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_property_repository
from app.core.errors import NotFoundError
from app.repositories.property_repository import PropertyRepository
from app.schemas.property import PropertyOut

router = APIRouter(tags=["properties"])


@router.get("/properties/{listing_id}", response_model=PropertyOut)
def get_property(
    listing_id: str, property_repo: PropertyRepository = Depends(get_property_repository)
) -> PropertyOut:
    listing = property_repo.get(listing_id)
    if listing is None:
        raise NotFoundError(f"Listing {listing_id} not found.")
    return PropertyOut.from_entity(listing)
