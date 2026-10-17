"""Domain-level exceptions and the structured error envelope.

PRD section 11: "All endpoints return structured errors with code, message, request_id." This
module defines the exception hierarchy once; ``app.main`` registers a single exception handler
that converts any ``HomerunError`` into that envelope, so individual routes never hand-roll
error JSON.
"""

from __future__ import annotations


class HomerunError(Exception):
    """Base class for all domain errors. ``code`` is a stable machine-readable identifier."""

    code: str = "internal_error"
    status_code: int = 500

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(HomerunError):
    code = "not_found"
    status_code = 404


class ValidationFailedError(HomerunError):
    code = "validation_failed"
    status_code = 422


class ConsentRequiredError(HomerunError):
    code = "consent_required"
    status_code = 403


class UnauthorizedChannelError(HomerunError):
    code = "unauthorized_channel"
    status_code = 403


class ListingIdentityMismatchError(HomerunError):
    """Raised when a client payload tries to swap listing_id/agent_id (handoff acceptance test)."""

    code = "listing_identity_mismatch"
    status_code = 409


class ProviderUnavailableError(HomerunError):
    """Upstream listing/LLM provider is down, rate-limited, or not authorized."""

    code = "provider_unavailable"
    status_code = 503


class ValuationUnsupportedError(HomerunError):
    code = "valuation_unsupported"
    status_code = 200  # not a failure — a labeled, expected outcome
