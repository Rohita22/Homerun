"""Request/response models for the Homerun UI endpoints (``/api/ui/*``)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import AgentTraceOut
from app.services.journey_ranker import DEFAULT_WEIGHTS

DEFAULT_TOWNS = ["Bishan", "Tampines", "Queenstown"]


class UIProfile(BaseModel):
    """The profile exactly as the buyer edits it on the "profile" screen."""

    budget: float = Field(default=900_000, ge=0)
    types: list[str] = Field(default_factory=lambda: ["HDB", "Condo"])
    towns: list[str] = Field(default_factory=lambda: list(DEFAULT_TOWNS))
    min_bed: int = Field(default=3, ge=0, le=10)
    weights: dict[str, float] = Field(default_factory=lambda: dict(DEFAULT_WEIGHTS))

    @field_validator("types")
    @classmethod
    def _known_types(cls, value: list[str]) -> list[str]:
        return [t for t in value if t in {"HDB", "Condo"}]


class MatchRequest(BaseModel):
    session_id: str
    profile: UIProfile
    limit: int = Field(default=5, ge=1, le=5)


class ChatTurnRequest(BaseModel):
    session_id: str
    message: str = Field(min_length=1, max_length=2000)
    profile: UIProfile | None = None  # the client's current edits, merged under the new message
    restart: bool = False  # first message of a fresh conversation: forget which questions were answered


class FeedbackTurnRequest(BaseModel):
    session_id: str
    profile: UIProfile
    a_id: str
    b_id: str
    pick: int | None = None  # 0 = A, 1 = B, 2 = neither
    tags: list[str] = Field(default_factory=list)  # any of price|area|commute|mrt


class FinanceTurnRequest(BaseModel):
    listing_id: str
    down_payment_pct: float = Field(default=25, ge=0, le=100)
    annual_rate_pct: float = Field(default=3.0, ge=0, le=20)
    years: int = Field(default=25, ge=1, le=35)


class CompareTurnRequest(FinanceTurnRequest):
    listing_id: str = ""  # unused here; ids carries the listings
    ids: list[str] = Field(min_length=2, max_length=3)


class InterestRequest(BaseModel):
    session_id: str
    listing_id: str


class HandoffTurnRequest(BaseModel):
    session_id: str
    listing_id: str
    channel: str = "original_listing"  # original_listing | authorized_direct_lead
    consent: bool = False
    fields: list[str] = Field(default_factory=list)  # name|email|phone|message


class ViewingCreate(BaseModel):
    session_id: str
    listing_id: str
    at_ms: int
    status: str = "self"


class ViewingPatch(BaseModel):
    checks: dict[str, bool] | None = None
    notes: str | None = Field(default=None, max_length=4000)


class PhotoCreate(BaseModel):
    image_data_url: str = Field(max_length=2_500_000)


class PhotoAnalysis(BaseModel):
    status: str  # done | error
    obs: dict[str, Any] | None = None
    reason: str | None = None


class UIResponse(BaseModel):
    trace: list[AgentTraceOut] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
