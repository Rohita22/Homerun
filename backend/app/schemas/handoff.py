"""Schemas for ``POST /api/handoffs/preview`` and ``POST /api/handoffs`` (PRD section 11 / 8).

Note deliberately: there is no ``agent_id`` field anywhere here. The server always derives the
agent from its own verified ``listing_agent_links`` lookup for the given ``listing_id`` — this
is what makes the "reject attempts to switch listing_id or agent_id from client payload"
acceptance test structurally impossible to violate rather than something checked at runtime.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.domain.enums import HandoffChannel


class HandoffPreviewRequest(BaseModel):
    listing_id: str


class ContactChoiceOut(BaseModel):
    channel: str
    requires_consent: bool


class HandoffPreviewResponse(BaseModel):
    listing_id: str
    association_status: str
    handoff_state: str
    safe_contact_choices: list[ContactChoiceOut]
    shared_field_preview: list[str]


class HandoffRequest(BaseModel):
    listing_id: str
    channel: HandoffChannel = HandoffChannel.ORIGINAL_LISTING
    consent: bool = False
    permitted_contact_fields: list[str] = Field(default_factory=list)
    buyer_contact: dict[str, str] = Field(default_factory=dict)


class HandoffResponse(BaseModel):
    handoff_id: str
    status: str
    destination_type: str
    contact_route: dict
