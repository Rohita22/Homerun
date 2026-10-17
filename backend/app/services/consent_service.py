"""Consent gating for buyer-contact sharing (PRD product principle: "No buyer contact sharing
without explicit granular consent"; section 8 handoff sequence: "show destination, precise
shared fields, purpose and explicit unticked opt-in").
"""

from __future__ import annotations

from app.core.errors import ConsentRequiredError, UnauthorizedChannelError
from app.domain.enums import HandoffChannel

CONSENT_VERSION = "v1"
SHAREABLE_BUYER_FIELDS = {"name", "phone", "email", "message"}


class ConsentService:
    def __init__(self, direct_lead_submission_enabled: bool) -> None:
        self._direct_lead_enabled = direct_lead_submission_enabled

    def validate_channel_allowed(self, channel: HandoffChannel) -> None:
        if channel == HandoffChannel.AUTHORIZED_DIRECT_LEAD and not self._direct_lead_enabled:
            raise UnauthorizedChannelError(
                "Direct lead submission is not authorized for this deployment; use the original "
                "listing contact route instead.",
                details={"channel": channel.value},
            )

    def validate_fields(self, requested_fields: list[str]) -> list[str]:
        invalid = [f for f in requested_fields if f not in SHAREABLE_BUYER_FIELDS]
        if invalid:
            raise ConsentRequiredError(
                f"Unsupported contact fields requested: {invalid}",
                details={"invalid_fields": invalid},
            )
        return requested_fields

    def require_consent(self, consent: bool) -> None:
        if not consent:
            raise ConsentRequiredError("Explicit buyer consent is required before any handoff.")
