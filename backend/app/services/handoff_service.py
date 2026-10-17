"""Agent handoff state machine and execution (PRD section 8).

``classify`` implements the state table exactly:

    AVAILABLE_VERIFIED        -> CONTACT_READY
    ASSOCIATION_UNVERIFIED    -> SOURCE_LISTING_ONLY
    AGENT_MISSING              -> SOURCE_LISTING_ONLY
    LISTING_INACTIVE           -> HALT_AND_RECHECK
    CONTACT_AUTHORIZATION_MISSING -> SOURCE_LISTING_ONLY

A CEA record can verify an agent's identity but never their relationship to a specific listing,
so a verified ``ListingAgentLink`` with provider-sourced evidence is required before any direct
contact channel is offered. ``execute`` enforces every PRD section 8 acceptance test: listing_id
and agent_id are always server-derived (never trusted from the client payload — the request
schema does not even accept an ``agent_id``), consent is mandatory, an unverified association
can never reach ``CONTACT_READY``, and a verified agent missing approved contact details falls
back to the original listing link instead of guessing.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.entities import Agent, ListingAgentLink, PropertyListing
from app.domain.enums import AssociationStatus, HandoffChannel, HandoffOutcome, HandoffState
from app.repositories.handoff_repository import HandoffRepository
from app.services.consent_service import SHAREABLE_BUYER_FIELDS, ConsentService


@dataclass
class HandoffClassification:
    state: HandoffState
    outcome: HandoffState
    agent: Agent | None
    link: ListingAgentLink | None


@dataclass
class HandoffDecision:
    handoff_id: str
    status: str
    destination_type: str
    contact_route: dict


def classify(
    listing: PropertyListing, agent_link: tuple[Agent, ListingAgentLink] | None
) -> HandoffClassification:
    listing_status = getattr(listing.status, "value", listing.status)
    if listing_status == "inactive":
        return HandoffClassification(
            HandoffState.LISTING_INACTIVE, HandoffState.HALT_AND_RECHECK, None, None
        )

    if agent_link is None:
        return HandoffClassification(
            HandoffState.AGENT_MISSING, HandoffState.SOURCE_LISTING_ONLY, None, None
        )

    agent, link = agent_link
    if link.association_status != AssociationStatus.VERIFIED:
        return HandoffClassification(
            HandoffState.ASSOCIATION_UNVERIFIED, HandoffState.SOURCE_LISTING_ONLY, agent, link
        )

    contact = agent.approved_contact or {}
    if not agent.name or not (contact.get("phone") or contact.get("email")):
        return HandoffClassification(
            HandoffState.CONTACT_AUTHORIZATION_MISSING,
            HandoffState.SOURCE_LISTING_ONLY,
            agent,
            link,
        )

    return HandoffClassification(
        HandoffState.AVAILABLE_VERIFIED, HandoffState.CONTACT_READY, agent, link
    )


class HandoffService:
    def __init__(self, repo: HandoffRepository, consent_service: ConsentService) -> None:
        self._repo = repo
        self._consent = consent_service

    def preview(
        self, listing: PropertyListing, agent_link: tuple[Agent, ListingAgentLink] | None
    ) -> dict:
        classification = classify(listing, agent_link)
        choices = [{"channel": HandoffChannel.ORIGINAL_LISTING.value, "requires_consent": False}]
        if classification.outcome == HandoffState.CONTACT_READY:
            choices.append(
                {"channel": HandoffChannel.AUTHORIZED_DIRECT_LEAD.value, "requires_consent": True}
            )
        return {
            "listing_id": listing.listing_id,
            "association_status": (
                classification.link.association_status.value
                if classification.link
                and hasattr(classification.link.association_status, "value")
                else (classification.link.association_status if classification.link else "missing")
            ),
            "handoff_state": classification.outcome.value,
            "safe_contact_choices": choices,
            "shared_field_preview": sorted(SHAREABLE_BUYER_FIELDS),
        }

    def execute(
        self,
        listing: PropertyListing,
        agent_link: tuple[Agent, ListingAgentLink] | None,
        requested_channel: HandoffChannel,
        consent: bool,
        requested_fields: list[str],
    ) -> HandoffDecision:
        classification = classify(listing, agent_link)

        if classification.outcome == HandoffState.HALT_AND_RECHECK:
            row = self._repo.create(
                listing.listing_id, None, requested_channel.value, HandoffOutcome.FAILED.value,
                consented=False,
            )
            return HandoffDecision(
                handoff_id=row.handoff_id,
                status="failed",
                destination_type="none",
                contact_route={
                    "reason": "Listing is no longer active; recheck before contacting an agent."
                },
            )

        effective_channel = requested_channel
        if (
            requested_channel == HandoffChannel.AUTHORIZED_DIRECT_LEAD
            and classification.outcome != HandoffState.CONTACT_READY
        ):
            # Never guess a missing/unverified agent's contact — fall back to the original
            # listing link instead (PRD acceptance test).
            effective_channel = HandoffChannel.ORIGINAL_LISTING

        if effective_channel == HandoffChannel.AUTHORIZED_DIRECT_LEAD:
            self._consent.validate_channel_allowed(effective_channel)
            self._consent.require_consent(consent)
            self._consent.validate_fields(requested_fields)

        if effective_channel == HandoffChannel.ORIGINAL_LISTING:
            if not listing.source_url:
                row = self._repo.create(
                    listing.listing_id, None, effective_channel.value, HandoffOutcome.FAILED.value,
                    consented=False,
                )
                return HandoffDecision(
                    handoff_id=row.handoff_id,
                    status="failed",
                    destination_type="none",
                    contact_route={"reason": "No original listing contact route is available."},
                )
            row = self._repo.create(
                listing.listing_id, None, effective_channel.value, HandoffOutcome.SUCCESS.value,
                consented=False,
            )
            return HandoffDecision(
                handoff_id=row.handoff_id,
                status="success",
                destination_type="original_listing",
                contact_route={"source_url": listing.source_url},
            )

        agent = classification.agent
        row = self._repo.create(
            listing.listing_id,
            agent.agent_id if agent else None,
            effective_channel.value,
            HandoffOutcome.SUCCESS.value,
            consented=True,
        )
        return HandoffDecision(
            handoff_id=row.handoff_id,
            status="success",
            destination_type="authorized_direct_lead",
            contact_route={
                "agent_name": agent.name,
                "shared_fields": requested_fields,
            },
        )
