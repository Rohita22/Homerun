"""Normalize one PropertyGuru search-result card (``listingsData[i].listingData`` inside the page's
``__NEXT_DATA__`` JSON) into the app's canonical ``PropertyListing``.

Only fields PropertyGuru prints on the public result card are used. Anything absent stays
``None`` (PRD: "treat missing/contradictory fields as unknown"); nothing is guessed except two
clearly-labelled derivations recorded in ``attributes`` (remaining lease from build year).
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from app.core.time import utcnow
from app.domain.entities import Agent, ListingAgentLink, PropertyListing
from app.domain.enums import AssociationStatus, ListingStatus, PropertyType, TransactionType
from app.scraper.towns import TownResolver

PROVIDER = "propertyguru_scraper"
SQFT_TO_SQM = 0.092903
_LANDED = ("terrace", "bungalow", "semi-detached", "semi detached", "townhouse", "cluster",
           "landed", "shophouse", "detached")
_BUILT_RE = re.compile(r"built:\s*(\d{4})", re.IGNORECASE)
_LEASE_YEARS_RE = re.compile(r"(\d+)\s*-?\s*year", re.IGNORECASE)


def _to_int(value: Any) -> int | None:
    try:
        return int(str(value).strip().replace(",", ""))
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> float | None:
    try:
        return float(str(value).strip().replace(",", ""))
    except (TypeError, ValueError):
        return None


def _property_type(sub_type: str | None, slug: str) -> PropertyType:
    text = (sub_type or "").lower()
    if "hdb" in text:
        return PropertyType.HDB
    if "executive" in text:
        return PropertyType.EC
    if any(k in text for k in _LANDED):
        return PropertyType.LANDED
    if text:
        return PropertyType.CONDO
    if slug.startswith("hdb-"):
        return PropertyType.HDB
    return PropertyType.CONDO


def _flat_type(bedrooms: int | None, property_type: PropertyType) -> str | None:
    # PropertyGuru counts bedrooms, HDB counts rooms (a "3 ROOM" flat has 2 bedrooms).
    if property_type != PropertyType.HDB or bedrooms is None:
        return None
    return {0: "2 ROOM", 1: "2 ROOM", 2: "3 ROOM", 3: "4 ROOM", 4: "5 ROOM"}.get(bedrooms, "EXECUTIVE")


def _features(card: dict) -> dict[str, str]:
    """``listingFeatures`` mixes dicts and one nested list; flatten into {dataAutomationId: text}."""
    out: dict[str, str] = {}

    def visit(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                visit(item)
        elif isinstance(node, dict) and node.get("dataAutomationId"):
            out[node["dataAutomationId"]] = str(node.get("text", ""))

    visit(card.get("listingFeatures"))
    return out


def slug_from_url(url: str | None) -> str | None:
    if not url or "/listing/" not in url:
        return None
    return url.split("/listing/", 1)[1].split("?", 1)[0].strip("/") or None


def parse_card(
    card: dict, resolver: TownResolver, now: datetime | None = None
) -> tuple[PropertyListing, Agent | None, ListingAgentLink | None] | None:
    now = now or utcnow()
    slug = slug_from_url(card.get("url"))
    if not slug:
        return None

    feats = _features(card)
    sub_type = (card.get("property") or {}).get("subTypeText") or feats.get("listing-card-v2-unit-type")
    property_type = _property_type(sub_type, slug)
    bedrooms = _to_int(card.get("bedrooms"))
    area_sqft = _to_float(card.get("floorArea"))
    if area_sqft is None:
        match = re.search(r"([\d,.]+)\s*sqft", feats.get("listing-card-v2-area", ""), re.IGNORECASE)
        area_sqft = _to_float(match.group(1)) if match else None

    tenure_text = feats.get("listing-card-v2-tenure") or None
    built_match = _BUILT_RE.search(feats.get("listing-card-v2-build-year", ""))
    built_year = int(built_match.group(1)) if built_match else None
    lease_years = None
    lease_note = None
    if tenure_text and built_year:
        years = _LEASE_YEARS_RE.search(tenure_text)
        if years and "leasehold" in tenure_text.lower() and int(years.group(1)) <= 99:
            lease_years = float(max(0, min(int(years.group(1)), int(years.group(1)) - (now.year - built_year))))
            lease_note = "estimated_from_build_year"

    area_label = (card.get("additionalData") or {}).get("districtText") or None
    full_address = card.get("fullAddress")
    if not area_label and full_address and "," in full_address:
        area_label = full_address.split(",", 1)[1].strip()
    title = card.get("localizedTitle")
    town = resolver.resolve(title, area_label) if property_type != PropertyType.LANDED else (
        resolver.resolve(None, area_label)
    )

    posted_unix = (card.get("postedOn") or {}).get("unix")
    published_at = datetime.fromtimestamp(posted_unix).replace(tzinfo=None) if posted_unix else None

    agent_raw = card.get("agent") or {}
    agent_id = f"propertyguru-agent-{agent_raw['id']}" if agent_raw.get("id") is not None else None

    status = ListingStatus.ACTIVE if card.get("statusCode") == "ACT" else ListingStatus.INACTIVE
    transaction = TransactionType.RENT if card.get("typeCode") == "RENT" else TransactionType.BUY

    listing = PropertyListing(
        listing_id=slug,
        provider=PROVIDER,
        external_id=str(card.get("id") or slug),
        source_url=card.get("url"),
        published_at=published_at,
        fetched_at=now,
        status=status,
        transaction_type=transaction,
        property_type=property_type,
        asking_price_sgd=_to_float((card.get("price") or {}).get("value")),
        bedrooms=bedrooms,
        bathrooms=_to_int(card.get("bathrooms")),
        floor_area_sqm=round(area_sqft * SQFT_TO_SQM, 1) if area_sqft else None,
        address_public=full_address,
        town=town,
        tenure=tenure_text,
        lease_remaining_years=lease_years,
        flat_type=_flat_type(bedrooms, property_type),
        attributes={
            "title": title,
            "sub_type": sub_type,
            "area_label": area_label,
            "district_code": (card.get("additionalData") or {}).get("districtCode"),
            "psf_text": card.get("psfText"),
            "built_year": built_year,
            "lease_remaining_source": lease_note,
            "price_type": ((card.get("price") or {}).get("type") or {}).get("text"),
            "mrt": (card.get("mrt") or {}).get("nearbyText") or None,
            "agency": (card.get("agency") or {}).get("name"),
        },
        images_allowed=False,
        agent_ref=agent_id,
        attribution="PropertyGuru Singapore (scraped public search results)",
        rights_status="scraped_display_only",
    )

    agent = link = None
    if agent_id:
        agent = Agent(
            agent_id=agent_id,
            provider_id=str(agent_raw["id"]),
            name=agent_raw.get("name"),
            cea_number=agent_raw.get("license"),
            approved_contact=None,  # never scraped or fabricated; handoff uses the listing link
            verified_at=None,
        )
        link = ListingAgentLink(
            listing_id=slug,
            agent_id=agent_id,
            evidence_source="propertyguru_search_card",
            association_status=AssociationStatus.VERIFIED,
            checked_at=now,
        )
    return listing, agent, link
