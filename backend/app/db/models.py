"""ORM models mirroring PRD section 10's database schema exactly (table names and primary
fields), plus the indexes it specifies.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import get_settings
from app.core.time import utcnow
from app.db.base import Base


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return utcnow()


def _session_expiry() -> datetime:
    return utcnow() + timedelta(hours=get_settings().session_ttl_hours)


class Session(Base):
    __tablename__ = "sessions"

    session_id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(default=_now)
    expires_at: Mapped[datetime] = mapped_column(default=_session_expiry)
    consent_version: Mapped[str] = mapped_column(String, default="v1")

    buyer_profile: Mapped["BuyerProfileRow | None"] = relationship(
        back_populates="session", uselist=False, cascade="all, delete-orphan"
    )


class BuyerProfileRow(Base):
    __tablename__ = "buyer_profiles"

    session_id: Mapped[str] = mapped_column(
        ForeignKey("sessions.session_id", ondelete="CASCADE"), primary_key=True
    )
    budget: Mapped[float | None] = mapped_column(Float, nullable=True)
    property_type: Mapped[str | None] = mapped_column(String, nullable=True)
    preferences_json: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(default=_now, onupdate=_now)

    session: Mapped["Session"] = relationship(back_populates="buyer_profile")


class PropertyRow(Base):
    __tablename__ = "properties"

    listing_id: Mapped[str] = mapped_column(String, primary_key=True)
    provider: Mapped[str] = mapped_column(String, index=True)
    external_id: Mapped[str] = mapped_column(String)
    source_url: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="unknown")
    type: Mapped[str] = mapped_column(String)  # property_type
    transaction_type: Mapped[str] = mapped_column(String, default="buy")
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    bedrooms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bathrooms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    floor_area: Mapped[float | None] = mapped_column(Float, nullable=True)
    address_public: Mapped[str | None] = mapped_column(String, nullable=True)
    town: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    tenure: Mapped[str | None] = mapped_column(String, nullable=True)
    lease_remaining_years: Mapped[float | None] = mapped_column(Float, nullable=True)
    floor_level: Mapped[str | None] = mapped_column(String, nullable=True)
    flat_type: Mapped[str | None] = mapped_column(String, nullable=True)
    flat_model: Mapped[str | None] = mapped_column(String, nullable=True)
    storey_range: Mapped[str | None] = mapped_column(String, nullable=True)
    attributes_json: Mapped[dict] = mapped_column(JSON, default=dict)
    images_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    agent_ref: Mapped[str | None] = mapped_column(String, nullable=True)
    attribution: Mapped[str | None] = mapped_column(String, nullable=True)
    rights_status: Mapped[str] = mapped_column(String, default="unknown")
    published_at: Mapped[datetime | None] = mapped_column(nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(default=_now)

    __table_args__ = (
        Index("ix_properties_type_price_status", "type", "price", "status"),
        UniqueConstraint("provider", "external_id", name="uq_properties_provider_external_id"),
    )


class AgentRow(Base):
    __tablename__ = "agents"

    agent_id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    provider_id: Mapped[str | None] = mapped_column(String, nullable=True)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    cea_number: Mapped[str | None] = mapped_column(String, nullable=True)
    approved_contact_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(nullable=True)


class ListingAgentLinkRow(Base):
    __tablename__ = "listing_agent_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    listing_id: Mapped[str] = mapped_column(ForeignKey("properties.listing_id"), index=True)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.agent_id"))
    evidence_source: Mapped[str] = mapped_column(String)
    association_status: Mapped[str] = mapped_column(String)
    checked_at: Mapped[datetime] = mapped_column(default=_now)

    __table_args__ = (
        Index("ix_listing_agent_links_listing_status", "listing_id", "association_status"),
    )


class RecommendationRunRow(Base):
    __tablename__ = "recommendation_runs"

    run_id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.session_id"))
    model_version: Mapped[str] = mapped_column(String)
    input_hash: Mapped[str] = mapped_column(String)
    produced_at: Mapped[datetime] = mapped_column(default=_now)

    items: Mapped[list["RecommendationItemRow"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class RecommendationItemRow(Base):
    __tablename__ = "recommendation_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("recommendation_runs.run_id"), index=True)
    listing_id: Mapped[str] = mapped_column(ForeignKey("properties.listing_id"))
    rank: Mapped[int] = mapped_column(Integer)
    score: Mapped[float] = mapped_column(Float)
    factors_json: Mapped[dict] = mapped_column(JSON, default=dict)

    run: Mapped["RecommendationRunRow"] = relationship(back_populates="items")


class FeedbackEventRow(Base):
    __tablename__ = "feedback_events"

    event_id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.session_id"), index=True)
    preferred_listing_id: Mapped[str | None] = mapped_column(String, nullable=True)
    rejected_listing_id: Mapped[str | None] = mapped_column(String, nullable=True)
    event_type: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(default=_now, index=True)


class LeadHandoffRow(Base):
    __tablename__ = "lead_handoffs"

    handoff_id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    listing_id: Mapped[str] = mapped_column(String)
    agent_id: Mapped[str | None] = mapped_column(String, nullable=True)
    contact_method: Mapped[str] = mapped_column(String)
    consent_at: Mapped[datetime | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(default=_now)


class AuditEventRow(Base):
    __tablename__ = "audit_events"

    event_id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    request_id: Mapped[str] = mapped_column(String, index=True)
    action: Mapped[str] = mapped_column(String)
    outcome: Mapped[str] = mapped_column(String)
    metadata_redacted_json: Mapped[dict] = mapped_column(JSON, default=dict)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    timestamp: Mapped[datetime] = mapped_column(default=_now)


class ScrapeRunRow(Base):
    """One execution of the PropertyGuru scraper (audit trail + "last refreshed" source)."""

    __tablename__ = "scrape_runs"

    run_id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    started_at: Mapped[datetime] = mapped_column(default=_now, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String, default="running")  # running|ok|partial|failed
    pages_ok: Mapped[int] = mapped_column(Integer, default=0)
    pages_failed: Mapped[int] = mapped_column(Integer, default=0)
    listings_seen: Mapped[int] = mapped_column(Integer, default=0)
    listings_deactivated: Mapped[int] = mapped_column(Integer, default=0)
    detail_json: Mapped[dict] = mapped_column(JSON, default=dict)


class ViewingRow(Base):
    """A planned/past property viewing for the "My move" hub (calendar, checklist, notes and
    AI-analysed photos). ``photos_json`` holds ``[{id, url, status, obs}]`` — kept inline because
    a viewing's photos are only ever read and written together with the viewing."""

    __tablename__ = "viewings"

    viewing_id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("sessions.session_id", ondelete="CASCADE"), index=True
    )
    listing_id: Mapped[str] = mapped_column(String)
    at_ms: Mapped[int] = mapped_column(Integer)  # epoch milliseconds (buyer's local wall time)
    status: Mapped[str] = mapped_column(String, default="self")  # confirmed|requested|self
    checks_json: Mapped[dict] = mapped_column(JSON, default=dict)
    notes: Mapped[str] = mapped_column(String, default="")
    photos_json: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(default=_now)


class EnquiryRow(Base):
    """What the buyer did about a listing (sent / redirected to source / failed) — the "enquiries"
    list in the hub. Never stores contact details, only the outcome and the handoff reference."""

    __tablename__ = "enquiries"

    enquiry_id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("sessions.session_id", ondelete="CASCADE"), index=True
    )
    listing_id: Mapped[str] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String)  # submitted|redirected|failed
    handoff_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_now)
