"""Property listing response schemas (PRD section 6 canonical fields + section 11 endpoints)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.domain.entities import PropertyListing


class PropertyOut(BaseModel):
    listing_id: str
    provider: str
    source_url: str | None
    status: str
    transaction_type: str
    property_type: str
    asking_price_sgd: float | None
    bedrooms: int | None
    bathrooms: int | None
    floor_area_sqm: float | None
    address_public: str | None
    town: str | None
    latitude: float | None
    longitude: float | None
    tenure: str | None
    lease_remaining_years: float | None
    floor_level: str | None
    attributes: dict[str, Any]
    images_allowed: bool
    attribution: str | None
    rights_status: str
    fetched_at: datetime
    has_coordinates: bool
    valuation_eligible: bool

    @staticmethod
    def from_entity(listing: PropertyListing) -> "PropertyOut":
        prop_type = getattr(listing.property_type, "value", listing.property_type)
        return PropertyOut(
            listing_id=listing.listing_id,
            provider=listing.provider,
            source_url=listing.source_url,
            status=getattr(listing.status, "value", listing.status),
            transaction_type=getattr(listing.transaction_type, "value", listing.transaction_type),
            property_type=prop_type,
            asking_price_sgd=listing.asking_price_sgd,
            bedrooms=listing.bedrooms,
            bathrooms=listing.bathrooms,
            floor_area_sqm=listing.floor_area_sqm,
            address_public=listing.address_public,
            town=listing.town,
            latitude=listing.latitude,
            longitude=listing.longitude,
            tenure=listing.tenure,
            lease_remaining_years=listing.lease_remaining_years,
            floor_level=listing.floor_level,
            attributes=listing.attributes,
            images_allowed=listing.images_allowed,
            attribution=listing.attribution,
            rights_status=listing.rights_status,
            fetched_at=listing.fetched_at,
            has_coordinates=listing.has_coordinates,
            valuation_eligible=(prop_type == "HDB"),
        )


class CompareRequest(BaseModel):
    listing_ids: list[str]


class CompareResponse(BaseModel):
    listings: list[PropertyOut]
    differences: dict[str, list[Any]]
    caveats: list[str]
