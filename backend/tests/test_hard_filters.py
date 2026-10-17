"""PRD section 14 functional test matrix: price and bedroom hard filters."""

from __future__ import annotations

from app.core.time import utcnow
from app.domain.entities import BuyerProfile, PropertyListing
from app.services.ranking_service import HardFilterService


def _listing(**overrides) -> PropertyListing:  # noqa: ANN003
    base = dict(
        listing_id="L1",
        provider="demo_fixture",
        external_id="L1",
        fetched_at=utcnow(),
        status="active",
        transaction_type="buy",
        property_type="HDB",
        asking_price_sgd=700_000,
        bedrooms=4,
        town="TAMPINES",
    )
    base.update(overrides)
    return PropertyListing.model_validate(base)


def test_price_701k_excluded_when_budget_700k() -> None:
    profile = BuyerProfile(session_id="s1", max_price_sgd=700_000, hard_constraints=["max_price_sgd"])
    listings = [_listing(listing_id="under", asking_price_sgd=700_000), _listing(listing_id="over", asking_price_sgd=701_000)]

    result = HardFilterService().apply(listings, profile)

    eligible_ids = {listing_.listing_id for listing_ in result.eligible}
    assert eligible_ids == {"under"}
    excluded_ids = {item["listing_id"] for item in result.excluded}
    assert excluded_ids == {"over"}


def test_four_room_requirement_excludes_three_room() -> None:
    profile = BuyerProfile(session_id="s1", min_bedrooms=4, hard_constraints=["min_bedrooms"])
    listings = [_listing(listing_id="four", bedrooms=4), _listing(listing_id="three", bedrooms=3)]

    result = HardFilterService().apply(listings, profile)

    assert {listing_.listing_id for listing_ in result.eligible} == {"four"}


def test_missing_price_goes_to_needs_confirmation_not_silently_included() -> None:
    profile = BuyerProfile(session_id="s1", max_price_sgd=700_000, hard_constraints=["max_price_sgd"])
    listings = [_listing(listing_id="unknown_price", asking_price_sgd=None)]

    result = HardFilterService().apply(listings, profile)

    assert result.eligible == []
    assert result.needs_confirmation[0]["listing_id"] == "unknown_price"


def test_property_type_mismatch_condo_never_matches_hdb_request() -> None:
    profile = BuyerProfile(session_id="s1", property_type="HDB")
    listings = [_listing(listing_id="condo", property_type="CONDO")]

    result = HardFilterService().apply(listings, profile)

    assert result.eligible == []
    assert "property_type" in result.excluded[0]["reasons"][0]


def test_inactive_listing_always_excluded() -> None:
    profile = BuyerProfile(session_id="s1")
    listings = [_listing(listing_id="stale", status="inactive")]

    result = HardFilterService().apply(listings, profile)

    assert result.eligible == []
