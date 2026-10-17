"""PRD section 8: handoff state machine + acceptance tests."""

from __future__ import annotations

from app.core.time import utcnow
from app.domain.entities import Agent, ListingAgentLink, PropertyListing
from app.domain.enums import AssociationStatus, HandoffState
from app.services.handoff_service import classify


def _listing(**overrides) -> PropertyListing:  # noqa: ANN003
    base = dict(
        listing_id="L1", provider="demo_fixture", external_id="L1", fetched_at=utcnow(),
        status="active", transaction_type="buy", property_type="HDB", source_url="https://x.invalid/1",
    )
    base.update(overrides)
    return PropertyListing.model_validate(base)


def _agent_link(association_status: AssociationStatus, has_contact: bool = True) -> tuple[Agent, ListingAgentLink]:
    agent = Agent(
        agent_id="a1", name="Agent One",
        approved_contact={"phone": "+65 8000 0000"} if has_contact else None,
    )
    link = ListingAgentLink(
        listing_id="L1", agent_id="a1", evidence_source="demo_fixture_provider",
        association_status=association_status, checked_at=utcnow(),
    )
    return agent, link


def test_verified_with_contact_is_contact_ready() -> None:
    result = classify(_listing(), _agent_link(AssociationStatus.VERIFIED))
    assert result.outcome == HandoffState.CONTACT_READY


def test_unverified_association_falls_back_to_source_listing() -> None:
    result = classify(_listing(), _agent_link(AssociationStatus.UNVERIFIED))
    assert result.outcome == HandoffState.SOURCE_LISTING_ONLY


def test_missing_agent_link_falls_back_to_source_listing() -> None:
    result = classify(_listing(), None)
    assert result.outcome == HandoffState.SOURCE_LISTING_ONLY


def test_inactive_listing_halts_and_rechecks() -> None:
    result = classify(_listing(status="inactive"), _agent_link(AssociationStatus.VERIFIED))
    assert result.outcome == HandoffState.HALT_AND_RECHECK


def test_verified_but_missing_contact_falls_back_to_source_listing() -> None:
    result = classify(_listing(), _agent_link(AssociationStatus.VERIFIED, has_contact=False))
    assert result.outcome == HandoffState.SOURCE_LISTING_ONLY


# --- API-level acceptance tests against the demo fixture catalog ---


def test_handoff_original_listing_succeeds_without_consent(client) -> None:  # noqa: ANN001
    response = client.post(
        "/api/handoffs", json={"listing_id": "fixture-101", "channel": "original_listing", "consent": False}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["destination_type"] == "original_listing"


def test_handoff_inactive_listing_halts(client) -> None:  # noqa: ANN001
    response = client.post(
        "/api/handoffs", json={"listing_id": "fixture-108", "channel": "original_listing", "consent": False}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "failed"


def test_handoff_missing_agent_falls_back_to_source_listing(client) -> None:  # noqa: ANN001
    response = client.post(
        "/api/handoffs", json={"listing_id": "fixture-105", "channel": "authorized_direct_lead", "consent": True}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["destination_type"] == "original_listing"


def test_direct_lead_rejected_when_not_authorized_by_deployment(client) -> None:  # noqa: ANN001
    # fixture-101 is CONTACT_READY, but direct_lead_submission_enabled defaults to False (PRD
    # section 16 open decision default).
    response = client.post(
        "/api/handoffs", json={"listing_id": "fixture-101", "channel": "authorized_direct_lead", "consent": True}
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "unauthorized_channel"


def test_handoff_preview_lists_only_safe_choices(client) -> None:  # noqa: ANN001
    response = client.post("/api/handoffs/preview", json={"listing_id": "fixture-104"})
    assert response.status_code == 200
    body = response.json()
    channels = {c["channel"] for c in body["safe_contact_choices"]}
    # fixture-104's association is "unverified" -> direct lead must never be offered.
    assert "authorized_direct_lead" not in channels


def test_handoff_unknown_listing_404(client) -> None:  # noqa: ANN001
    response = client.post("/api/handoffs/preview", json={"listing_id": "does-not-exist"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
