"""Scraper tests: parsing real captured PropertyGuru cards, town resolution, and DB upsert.
No network and no browser — the Playwright fetcher is exercised by the live run instead."""

from __future__ import annotations

import json
from pathlib import Path

from app.core.time import utcnow
from app.db.base import SessionLocal, init_db
from app.repositories.property_repository import PropertyRepository
from app.scraper.fetcher import PageBlockedError, extract_page, page_url
from app.scraper.parser import PROVIDER, parse_card, slug_from_url
from app.scraper.towns import TownResolver, normalize_street, split_block_and_street, towns_in_label

import pytest

CARDS = json.loads((Path(__file__).parent / "fixtures" / "propertyguru_cards.json").read_text())


def _resolver(tmp_path: Path) -> TownResolver:
    csv_path = tmp_path / "resale.csv"
    csv_path.write_text(
        "month,town,flat_type,block,street_name,storey_range,floor_area_sqm,flat_model,"
        "lease_commence_date,remaining_lease,resale_price\n"
        "2026-01,CLEMENTI,4 ROOM,335,CLEMENTI AVE 2,01 TO 03,90,Improved,1978,50 years,500000\n"
        "2026-01,BUKIT PANJANG,5 ROOM,549A,SEGAR RD,10 TO 12,110,Model A,2010,80 years,600000\n"
    )
    return TownResolver(csv_path)


def test_street_normalization_matches_hdb_abbreviations():
    assert normalize_street("Clementi Avenue 2") == normalize_street("CLEMENTI AVE 2")
    assert split_block_and_street("549A Segar Road") == ("549A", "Segar Road")
    assert split_block_and_street("Lake Life") == (None, "Lake Life")


def test_town_from_resale_lookup_beats_ambiguous_label(tmp_path):
    resolver = _resolver(tmp_path)
    # the label alone names three towns; the block+street lookup is exact
    assert resolver.resolve("549A Segar Road", "Dairy Farm / Bukit Panjang / Choa Chu Kang") == "BUKIT PANJANG"
    assert towns_in_label("Hougang / Punggol / Sengkang") == {"HOUGANG", "PUNGGOL", "SENGKANG"}
    assert resolver.resolve("1 Unknown Road", "Hougang / Punggol / Sengkang") is None  # stays unknown
    assert resolver.resolve("1 Unknown Road", "Bedok / Upper East Coast") == "BEDOK"


def test_parse_hdb_card(tmp_path):
    listing, agent, link = parse_card(CARDS[0], _resolver(tmp_path), utcnow())
    assert listing.provider == PROVIDER
    assert listing.listing_id == slug_from_url(CARDS[0]["url"])
    assert listing.property_type.value == "HDB"
    assert listing.transaction_type.value == "buy"
    assert listing.status.value == "active"
    assert listing.town == "CLEMENTI"
    assert listing.asking_price_sgd == 470000
    assert listing.bedrooms == 2 and listing.flat_type == "3 ROOM"
    assert listing.floor_area_sqm == pytest.approx(732 * 0.092903, abs=0.1)
    assert listing.tenure == "99-year Leasehold"
    assert listing.lease_remaining_years == 99 - (utcnow().year - 1978)
    assert listing.attributes["lease_remaining_source"] == "estimated_from_build_year"
    assert agent is not None and agent.approved_contact is None  # never fabricated
    assert link.listing_id == listing.listing_id


def test_card_without_url_is_skipped(tmp_path):
    assert parse_card({"localizedTitle": "x"}, _resolver(tmp_path)) is None


def test_extract_page_detects_challenge_and_parses_data():
    with pytest.raises(PageBlockedError):
        extract_page("<html><title>Just a moment...</title></html>")
    payload = {"props": {"pageProps": {"pageData": {"data": {
        "listingsData": [{"listingData": CARDS[0]}],
        "paginationData": {"currentPage": 2, "totalPages": 9},
    }}}}}
    html = f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(payload)}</script>'
    result = extract_page(html)
    assert (result.current_page, result.total_pages, len(result.cards)) == (2, 9, 1)


def test_page_url_has_no_query_string():
    assert page_url("hdb-for-sale", 1).endswith("/hdb-for-sale")
    assert page_url("/hdb-for-sale/", 3).endswith("/hdb-for-sale/3")
    assert "?" not in page_url("hdb-for-sale", 3)


def test_upsert_is_idempotent_and_stale_listings_deactivate(tmp_path, client, seed_inventory):
    init_db()
    db = SessionLocal()
    try:
        repo = PropertyRepository(db)
        baseline = repo.count(PROVIDER)  # fixture inventory seeded into the shared test DB
        now = utcnow()
        for _ in range(2):  # a second run must update in place, not duplicate
            for card in CARDS:
                listing, agent, link = parse_card(card, _resolver(tmp_path), now)
                repo.upsert(listing)
                repo.upsert_agent(agent)
                db.flush()
                repo.replace_link(link)
            db.commit()
        assert repo.count(PROVIDER) == baseline + 3
        active_before = repo.count(PROVIDER, status="active")
        assert repo.get_agent_link(slug_from_url(CARDS[0]["url"])) is not None

        from datetime import timedelta

        assert repo.deactivate_unseen(PROVIDER, now - timedelta(hours=1)) == 0
        assert repo.deactivate_unseen(PROVIDER, now + timedelta(hours=1)) == active_before
        db.commit()
        assert repo.count(PROVIDER, status="active") == 0
    finally:
        db.close()
        seed_inventory()


def test_dead_running_row_does_not_block_schedule():
    from app.core.config import get_settings
    from app.db.models import ScrapeRunRow
    from app.scraper.service import seconds_until_due

    init_db()
    db = SessionLocal()
    try:
        db.query(ScrapeRunRow).delete()
        db.add(ScrapeRunRow(started_at=utcnow(), status="running", detail_json={"pid": 2_999_999}))
        db.commit()
        assert seconds_until_due(get_settings()) == 0  # crashed run ignored -> due now

        import os

        db.add(ScrapeRunRow(started_at=utcnow(), finished_at=utcnow(), status="ok", detail_json={}))
        db.commit()
        assert seconds_until_due(get_settings()) > 11 * 3600  # fresh success -> next run in ~12h
        db.add(ScrapeRunRow(started_at=utcnow(), status="running", detail_json={"pid": os.getpid()}))
        db.commit()
        assert seconds_until_due(get_settings()) == 300  # live run in progress
    finally:
        db.query(ScrapeRunRow).delete()
        db.commit()
        db.close()


def _card_with_media(tmp_path, **media):
    card = {**CARDS[0], **media}
    return parse_card(card, _resolver(tmp_path), utcnow())[0]


def test_photo_links_are_kept_as_direct_https_cdn_urls(tmp_path):
    listing = _card_with_media(
        tmp_path,
        thumbnail="https://sg1-cdn.pgimgs.com/listing/1/UPHO.1.V550.jpg",
        mediaCarousel={"previewMedia": {"images": {"items": [
            {"src": "https://sg1-cdn.pgimgs.com/listing/1/UPHO.1.V800/a.jpg", "caption": ""},
            {"src": "http://insecure.example/x.jpg"},   # not https -> dropped
            {"caption": "no src"},
            {"src": "https://sg1-cdn.pgimgs.com/listing/1/UPHO.2.V800/a.jpg"},
        ] + [{"src": f"https://sg1-cdn.pgimgs.com/p{i}.jpg"} for i in range(20)]}}},
    )
    attrs = listing.attributes
    assert attrs["thumbnail"].endswith("V550.jpg")
    assert attrs["photos"][:2] == [
        "https://sg1-cdn.pgimgs.com/listing/1/UPHO.1.V800/a.jpg",
        "https://sg1-cdn.pgimgs.com/listing/1/UPHO.2.V800/a.jpg",
    ]
    assert len(attrs["photos"]) == 10 and all(u.startswith("https://") for u in attrs["photos"])


def test_card_without_media_has_no_photos_not_a_placeholder(tmp_path):
    listing = _card_with_media(tmp_path)
    assert listing.attributes["photos"] == [] and listing.attributes["thumbnail"] is None


def test_listing_view_exposes_thumb_and_gallery(tmp_path):
    from app.journey.views import listing_view

    view = listing_view(_card_with_media(
        tmp_path, thumbnail="https://sg1-cdn.pgimgs.com/t.jpg",
        mediaCarousel={"previewMedia": {"images": {"items": [{"src": "https://sg1-cdn.pgimgs.com/g1.jpg"}]}}},
    ))
    assert view["thumb"] == "https://sg1-cdn.pgimgs.com/g1.jpg"  # no size token in this URL -> unchanged
    assert view["photos"] == ["https://sg1-cdn.pgimgs.com/g1.jpg"]
    sized = listing_view(_card_with_media(
        tmp_path, mediaCarousel={"previewMedia": {"images": {"items": [
            {"src": "https://sg1-cdn.pgimgs.com/listing/9/UPHO.1.V800/x.jpg"}]}}}))
    assert sized["thumb"].endswith("UPHO.1.V800/x.jpg") and sized["photos"][0].endswith("UPHO.1.V1024/x.jpg")
    bare = listing_view(_card_with_media(tmp_path))
    assert bare["thumb"] is None and bare["photos"] == []


def test_sync_listing_distinguishes_new_updated_unchanged(tmp_path):
    from app.scraper.service import _sync_listing

    init_db()
    resolver = TownResolver(tmp_path / "none.csv")
    listing, _, _ = parse_card(CARDS[0], resolver)
    db = SessionLocal()
    try:
        repo = PropertyRepository(db)
        now = utcnow()
        _sync_listing(db, repo, listing, now)  # new, or already seeded by an earlier test
        db.flush()
        assert _sync_listing(db, repo, listing, now) == "unchanged"
        listing.asking_price_sgd = (listing.asking_price_sgd or 0) + 1000
        assert _sync_listing(db, repo, listing, now) == "updated"
    finally:
        db.rollback()
        db.close()
