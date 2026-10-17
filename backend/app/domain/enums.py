"""Enumerated categories shared across the domain, API and persistence layers.

Keeping these in one place (rather than re-declaring string literals per layer) is what lets the
PRD's "enumerated categories and missing/null distinction" normalization rule (section 6) hold
everywhere automatically.
"""

from __future__ import annotations

from enum import StrEnum


class TransactionType(StrEnum):
    BUY = "buy"
    RENT = "rent"


class PropertyType(StrEnum):
    HDB = "HDB"
    CONDO = "CONDO"
    LANDED = "LANDED"
    EC = "EC"  # executive condominium


class ListingStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    UNKNOWN = "unknown"


class SourceMode(StrEnum):
    LIVE_AUTHORIZED = "live_authorized"
    DEMO_FIXTURE = "demo_fixture"


class ValuationStatus(StrEnum):
    SUPPORTED_HDB = "supported_hdb"
    UNSUPPORTED_PROPERTY_TYPE = "unsupported_property_type"
    INSUFFICIENT_FEATURES = "insufficient_features"
    MODEL_UNAVAILABLE = "model_unavailable"


class AssociationStatus(StrEnum):
    """PRD section 8: agent-listing association evidence states."""

    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    MISSING = "missing"
    STALE = "stale"


class HandoffState(StrEnum):
    """PRD section 8 state machine."""

    AVAILABLE_VERIFIED = "AVAILABLE_VERIFIED"
    CONTACT_READY = "CONTACT_READY"
    ASSOCIATION_UNVERIFIED = "ASSOCIATION_UNVERIFIED"
    SOURCE_LISTING_ONLY = "SOURCE_LISTING_ONLY"
    AGENT_MISSING = "AGENT_MISSING"
    LISTING_INACTIVE = "LISTING_INACTIVE"
    HALT_AND_RECHECK = "HALT_AND_RECHECK"
    CONTACT_AUTHORIZATION_MISSING = "CONTACT_AUTHORIZATION_MISSING"


class HandoffChannel(StrEnum):
    ORIGINAL_LISTING = "original_listing"
    AUTHORIZED_DIRECT_LEAD = "authorized_direct_lead"


class HandoffOutcome(StrEnum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    DECLINED = "declined"


class FeedbackEventType(StrEnum):
    LIKE = "like"
    REJECT = "reject"
    PAIRWISE_CHOICE = "pairwise_choice"


class AgentResultStatus(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"
    ERROR = "error"
