"""``POST /api/handoffs/preview`` and ``POST /api/handoffs`` (PRD section 11 / 8).

Every handoff is recorded to the audit log with a redacted metadata payload (never raw buyer
contact fields), per PRD section 9: "Mask personal contact information in logs"."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import (
    get_audit_repository,
    get_handoff_service,
    get_property_repository,
    get_request_id,
)
from app.core.errors import NotFoundError
from app.repositories.audit_repository import AuditRepository
from app.repositories.property_repository import PropertyRepository
from app.schemas.handoff import (
    ContactChoiceOut,
    HandoffPreviewRequest,
    HandoffPreviewResponse,
    HandoffRequest,
    HandoffResponse,
)
from app.services.handoff_service import HandoffService

router = APIRouter(tags=["handoffs"])


def _get_listing_or_404(listing_id: str, property_repo: PropertyRepository):  # noqa: ANN201
    listing = property_repo.get(listing_id)
    if listing is None:
        raise NotFoundError(f"Listing {listing_id} not found.")
    return listing


@router.post("/handoffs/preview", response_model=HandoffPreviewResponse)
def post_handoff_preview(
    body: HandoffPreviewRequest,
    property_repo: PropertyRepository = Depends(get_property_repository),
    handoff_service: HandoffService = Depends(get_handoff_service),
) -> HandoffPreviewResponse:
    listing = _get_listing_or_404(body.listing_id, property_repo)
    agent_link = property_repo.get_agent_link(body.listing_id)
    preview = handoff_service.preview(listing, agent_link)
    return HandoffPreviewResponse(
        listing_id=preview["listing_id"],
        association_status=preview["association_status"],
        handoff_state=preview["handoff_state"],
        safe_contact_choices=[ContactChoiceOut(**c) for c in preview["safe_contact_choices"]],
        shared_field_preview=preview["shared_field_preview"],
    )


@router.post("/handoffs", response_model=HandoffResponse)
def post_handoff(
    body: HandoffRequest,
    request_id: str = Depends(get_request_id),
    property_repo: PropertyRepository = Depends(get_property_repository),
    handoff_service: HandoffService = Depends(get_handoff_service),
    audit_repo: AuditRepository = Depends(get_audit_repository),
) -> HandoffResponse:
    listing = _get_listing_or_404(body.listing_id, property_repo)
    agent_link = property_repo.get_agent_link(body.listing_id)

    decision = handoff_service.execute(
        listing=listing,
        agent_link=agent_link,
        requested_channel=body.channel,
        consent=body.consent,
        requested_fields=body.permitted_contact_fields,
    )

    audit_repo.record(
        request_id=request_id,
        action="handoff",
        outcome=decision.status,
        metadata_redacted={
            "listing_id": body.listing_id,
            "channel": decision.destination_type,
            "handoff_id": decision.handoff_id,
            "fields_requested_count": len(body.permitted_contact_fields),
        },
    )

    return HandoffResponse(
        handoff_id=decision.handoff_id,
        status=decision.status,
        destination_type=decision.destination_type,
        contact_route=decision.contact_route,
    )
