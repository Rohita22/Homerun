"""Core domain entities.

These are the shapes every layer (providers, agents, services, repositories, API) agrees on.
They are plain Pydantic models with no persistence or transport concerns, so the ORM layer
(``app.db.models``) and the API layer (``app.schemas``) both map onto them instead of leaking
SQLAlchemy columns or HTTP concerns into business logic.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from app.core.time import utcnow
from app.domain.enums import (
    AssociationStatus,
    ListingStatus,
    PropertyType,
    TransactionType,
)


class BuyerProfile(BaseModel):
    """Structured buyer requirements extracted from chat or submitted via the preference form.

    ``hard_constraints`` lists which fields among {property_type, max_price_sgd, min_bedrooms,
    preferred_towns, transaction_type} are non-negotiable; everything else is a soft preference
    weighted by ``soft_weights``. Separating the two is required by PRD section 7A.
    """

    session_id: str
    transaction_type: TransactionType = TransactionType.BUY
    property_type: PropertyType | None = None
    max_price_sgd: float | None = Field(default=None, gt=0)
    min_price_sgd: float | None = Field(default=None, ge=0)
    min_bedrooms: int | None = Field(default=None, ge=0)
    min_bathrooms: int | None = Field(default=None, ge=0)
    min_floor_area_sqm: float | None = Field(default=None, ge=0)
    preferred_towns: list[str] = Field(default_factory=list)
    hard_constraints: list[str] = Field(default_factory=list)
    soft_weights: dict[str, float] = Field(default_factory=dict)
    notes: str | None = None
    updated_at: datetime = Field(default_factory=utcnow)

    def is_hard(self, field: str) -> bool:
        return field in self.hard_constraints


class PropertyListing(BaseModel):
    """Canonical normalized listing (PRD section 6 field list)."""

    model_config = ConfigDict(from_attributes=True)

    listing_id: str
    provider: str
    external_id: str
    source_url: str | None = None
    published_at: datetime | None = None
    fetched_at: datetime
    status: ListingStatus = ListingStatus.UNKNOWN
    transaction_type: TransactionType = TransactionType.BUY
    property_type: PropertyType
    asking_price_sgd: float | None = None
    bedrooms: int | None = None
    bathrooms: int | None = None
    floor_area_sqm: float | None = None
    address_public: str | None = None
    town: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    tenure: str | None = None
    lease_remaining_years: float | None = None
    floor_level: str | None = None
    flat_type: str | None = None
    flat_model: str | None = None
    storey_range: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    images_allowed: bool = False
    agent_ref: str | None = None
    attribution: str | None = None
    rights_status: str = "unknown"

    @property
    def has_coordinates(self) -> bool:
        return self.latitude is not None and self.longitude is not None


class Agent(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    agent_id: str
    provider_id: str | None = None
    name: str | None = None
    cea_number: str | None = None
    approved_contact: dict[str, str] | None = None  # e.g. {"phone": "...", "email": "..."}
    verified_at: datetime | None = None


class ListingAgentLink(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    listing_id: str
    agent_id: str
    evidence_source: str
    association_status: AssociationStatus
    checked_at: datetime


class ValuationResult(BaseModel):
    status: str
    point_estimate_sgd: float | None = None
    interval_low_sgd: float | None = None
    interval_high_sgd: float | None = None
    coverage_note: str | None = None
    comparable_listing_ids: list[str] = Field(default_factory=list)
    model_version: str | None = None
    reason: str | None = None


class FinanceEstimate(BaseModel):
    monthly_payment_sgd: float
    loan_principal_sgd: float
    down_payment_sgd: float
    annual_rate_pct: float
    tenure_years: int
    scenarios: list[dict[str, Any]] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)


class RankedItem(BaseModel):
    listing_id: str
    rank: int
    score: float
    reasons: list[str] = Field(default_factory=list)
    factors: dict[str, float] = Field(default_factory=dict)
    valuation_status: str | None = None
    valuation: ValuationResult | None = None


TData = TypeVar("TData")


class AgentResult(BaseModel, Generic[TData]):
    """Typed envelope every agent returns (PRD section 5 orchestration contracts)."""

    request_id: str
    agent_name: str
    status: str
    data: TData | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    elapsed_ms: float = 0.0
    model_version: str | None = None
