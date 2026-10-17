"""Schemas for ``POST /api/recommendations`` and ``POST /api/feedback`` (PRD section 11)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.buyer import BuyerProfileIn
from app.schemas.common import AgentTraceOut


class RecommendationRequest(BaseModel):
    session_id: str
    profile: BuyerProfileIn | None = None  # optional override; falls back to stored profile
    limit: int = Field(default=5, ge=1, le=5)


class ValuationOut(BaseModel):
    status: str
    point_estimate_sgd: float | None = None
    interval_low_sgd: float | None = None
    interval_high_sgd: float | None = None
    coverage_note: str | None = None
    model_version: str | None = None
    reason: str | None = None


class RecommendationItemOut(BaseModel):
    listing_id: str
    rank: int
    score: float
    reasons: list[str]
    factors: dict[str, float]
    valuation_status: str | None = None
    valuation: ValuationOut | None = None
    address_public: str | None = None
    asking_price_sgd: float | None = None
    town: str | None = None


class RecommendationResponse(BaseModel):
    run_id: str
    session_id: str
    source_mode: str
    requested_count: int
    returned_count: int
    items: list[RecommendationItemOut]
    excluded_count: int
    needs_confirmation_count: int
    warnings: list[str] = Field(default_factory=list)
    trace: list[AgentTraceOut] = Field(default_factory=list)


class FeedbackRequest(BaseModel):
    session_id: str
    chosen_id: str
    rejected_id: str | None = None
    event_type: str = "pairwise_choice"  # "like" | "reject" | "pairwise_choice"


class FeedbackResponse(BaseModel):
    updated_weights: dict[str, float]
    new_run_id: str
    items: list[RecommendationItemOut]
    trace: list[AgentTraceOut] = Field(default_factory=list)
