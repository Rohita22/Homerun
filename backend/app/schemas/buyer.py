"""Request/response schemas for buyer profile endpoints (PRD section 11:
``PUT /api/preferences``) and the preference-review screen (PRD section 4)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.domain.enums import PropertyType, TransactionType


class BuyerProfileIn(BaseModel):
    transaction_type: TransactionType = TransactionType.BUY
    property_type: PropertyType | None = None
    property_types: list[PropertyType] = Field(default_factory=list)
    max_price_sgd: float | None = Field(default=None, gt=0)
    min_price_sgd: float | None = Field(default=None, ge=0)
    min_bedrooms: int | None = Field(default=None, ge=0)
    min_bathrooms: int | None = Field(default=None, ge=0)
    min_floor_area_sqm: float | None = Field(default=None, ge=0)
    preferred_towns: list[str] = Field(default_factory=list)
    hard_constraints: list[str] = Field(default_factory=list)
    soft_weights: dict[str, float] = Field(default_factory=dict)
    notes: str | None = None


class BuyerProfileOut(BuyerProfileIn):
    session_id: str
