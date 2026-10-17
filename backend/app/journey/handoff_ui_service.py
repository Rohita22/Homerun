"""Interest checks and the agent handoff, shaped for the "interest -> contact -> outcome" screens.

Both go through the PRD's handoff state machine (:mod:`app.services.handoff_service`): the agent
is always derived server-side from the listing, direct contact is offered only when it is verified
*and* has an authorised contact route, and everything else falls back to the original listing.
Outcomes are recorded for the hub's "enquiries" list; contact details are never stored.
"""

from __future__ import annotations

from app.core.errors import NotFoundError
from app.domain.enums import HandoffChannel
from app.journey.views import agent_state
from app.repositories.property_repository import PropertyRepository
from app.repositories.session_repository import SessionRepository
from app.repositories.ui_repository import EnquiryRepository
from app.services.handoff_service import HandoffService


class HandoffUiService:
    def __init__(
        self,
        property_repo: PropertyRepository,
        handoff_service: HandoffService,
        enquiries: EnquiryRepository,
        sessions: SessionRepository,
    ) -> None:
        self._sessions = sessions
        self._properties = property_repo
        self._handoffs = handoff_service
        self._enquiries = enquiries

    def _listing(self, listing_id: str):  # noqa: ANN202
        listing = self._properties.get(listing_id)
        if listing is None:
            raise NotFoundError(f"Listing {listing_id} not found.")
        return listing

    def interest(self, listing_id: str) -> dict:
        listing = self._listing(listing_id)
        agent = agent_state(listing, self._properties.get_agent_link(listing_id))
        active = getattr(listing.status, "value", listing.status) == "active"
        return {
            "listing_id": listing_id,
            "still_listed": {"ok": active, "as_of": listing.fetched_at.isoformat()},
            "agent": agent,
            "source_url": listing.source_url,
            "direct_contact": agent["st"] == "verified",
        }

    def submit(
        self, session_id: str, listing_id: str, channel: str, consent: bool, fields: list[str]
    ) -> dict:
        listing = self._listing(listing_id)
        agent_link = self._properties.get_agent_link(listing_id)
        decision = self._handoffs.execute(
            listing=listing,
            agent_link=agent_link,
            requested_channel=HandoffChannel(channel),
            consent=consent,
            requested_fields=fields,
        )
        if decision.status != "success":
            kind = "failed"
        elif decision.destination_type == "authorized_direct_lead":
            kind = "submitted"
        else:
            kind = "redirected"
        self._sessions.get_or_create(session_id)  # enquiries hang off a session row
        self._enquiries.record(session_id, listing_id, kind, decision.handoff_id)
        return {
            "outcome": kind,
            "ref": f"req_{decision.handoff_id[:8]}",
            "destination": decision.destination_type,
            "agent_name": (agent_link[0].name if agent_link else None),
            "source_url": listing.source_url if kind == "redirected" else None,
            "reason": decision.contact_route.get("reason"),
        }
