"""Listing -> UI view model.

One place decides how a canonical :class:`PropertyListing` is presented to the Homerun UI: the
display name, "HDB 4-room" type label, MRT minutes parsed from the scraped text, commute estimate,
schematic map position, valuation range and the agent-verification state. Anything the source did
not provide stays ``None`` so the UI can say "unknown" instead of showing a guess.
"""

from __future__ import annotations

import re
from typing import Any

from app.domain.entities import Agent, ListingAgentLink, PropertyListing, ValuationResult
from app.domain.enums import HandoffState
from app.journey.geo import commute_estimate, map_position
from app.ml.comps import comparable_resales
from app.services.handoff_service import classify

_MRT_MIN_RE = re.compile(r"\((\d+)\s*min\)", re.IGNORECASE)
_MRT_NAME_RE = re.compile(r"from\s+(?:[A-Z]{1,3}\d+\s+)?(.+)$", re.IGNORECASE)
UI_TYPES = {"HDB": "HDB", "CONDO": "Condo", "EC": "Condo"}  # LANDED is out of the UI's scope


def in_ui_scope(listing: PropertyListing) -> bool:
    ptype = getattr(listing.property_type, "value", listing.property_type)
    status = getattr(listing.status, "value", listing.status)
    return ptype in UI_TYPES and status == "active"


def ui_category(listing: PropertyListing) -> str:
    return UI_TYPES.get(getattr(listing.property_type, "value", listing.property_type), "Condo")


def parse_mrt(text: str | None) -> tuple[int | None, str | None]:
    if not text:
        return None, None
    minutes = _MRT_MIN_RE.search(text)
    name = _MRT_NAME_RE.search(text)
    return (int(minutes.group(1)) if minutes else None), (name.group(1).strip() if name else None)


def _display_name(listing: PropertyListing) -> str:
    title = (listing.attributes or {}).get("title") or (listing.address_public or "").split(",")[0]
    title = (title or listing.listing_id).strip()
    if ui_category(listing) == "HDB" and re.match(r"^\d+[A-Za-z]?\s", title):
        return f"Blk {title}"
    return title


def _type_label(listing: PropertyListing) -> str:
    ptype = getattr(listing.property_type, "value", listing.property_type)
    if ptype == "HDB":
        flat = (listing.flat_type or "").upper()
        if flat.endswith(" ROOM"):
            return f"HDB {flat.split()[0]}-room"
        return "HDB Executive" if flat == "EXECUTIVE" else "HDB"
    return "Executive Condo" if ptype == "EC" else "Condo"


def _tenure_label(tenure: str | None) -> str | None:
    if not tenure:
        return None
    match = re.match(r"(\d+)\s*-?\s*year", tenure, re.IGNORECASE)
    if match:
        return f"{match.group(1)}-yr"
    return "Freehold" if "freehold" in tenure.lower() else tenure


def agent_state(
    listing: PropertyListing, agent_link: tuple[Agent, ListingAgentLink] | None
) -> dict[str, Any]:
    """verified = the handoff state machine would offer a direct, consented channel."""
    classification = classify(listing, agent_link)
    agent = agent_link[0] if agent_link else None
    if classification.outcome == HandoffState.CONTACT_READY:
        state = "verified"
    elif agent_link is None:
        state = "missing"
    else:
        state = "unverified"
    return {
        "st": state,
        "name": agent.name if agent else None,
        "cea": agent.cea_number if agent else None,
        "handoff_state": classification.outcome.value,
    }


def valuation_view(listing: PropertyListing, valuation: ValuationResult | None) -> dict | None:
    if (
        valuation is None
        or valuation.status != "supported_hdb"
        or valuation.point_estimate_sgd is None
        or valuation.interval_low_sgd is None
        or valuation.interval_high_sgd is None
    ):
        return None
    return {
        "pt": valuation.point_estimate_sgd,
        "lo": valuation.interval_low_sgd,
        "hi": valuation.interval_high_sgd,
        "n": comparable_resales(listing.town, listing.flat_type),
        "model": valuation.model_version,
        "note": valuation.coverage_note,
    }


def _resize(url: str, size: str) -> str:
    """PropertyGuru's CDN serves each photo at fixed widths named in the path (V550, V800, V1024)."""
    return re.sub(r"\.V\d+(?=[/.])", f".{size}", url, count=1)


def _photos(attrs: dict) -> tuple[str | None, list[str]]:
    """(card thumbnail, gallery): sharper variants than the card's own, same photos."""
    raw = [u for u in attrs.get("photos") or [] if isinstance(u, str)]
    thumb = attrs.get("thumbnail")
    if raw:
        thumb = _resize(raw[0], "V800")
    return thumb, [_resize(u, "V1024") for u in raw] or ([thumb] if thumb else [])


def listing_view(
    listing: PropertyListing,
    agent_link: tuple[Agent, ListingAgentLink] | None = None,
    valuation: ValuationResult | None = None,
) -> dict[str, Any]:
    attrs = listing.attributes or {}
    mrt_min, mrt_name = parse_mrt(attrs.get("mrt"))
    commute, basis = commute_estimate(listing.latitude, listing.longitude, listing.town)
    lease = listing.lease_remaining_years
    thumb, gallery = _photos(attrs)
    return {
        "id": listing.listing_id,
        "name": _display_name(listing),
        "town": (listing.town or "").title() or None,
        "cat": ui_category(listing),
        "type": _type_label(listing),
        "beds": listing.bedrooms,
        "price": listing.asking_price_sgd,
        "area": round(listing.floor_area_sqm) if listing.floor_area_sqm else None,
        "tenure": _tenure_label(listing.tenure),
        "lease": f"{int(lease)} yrs" if lease is not None else None,
        "floor": listing.storey_range or listing.floor_level,
        "mrt": mrt_min,
        "mrt_name": mrt_name,
        "commute": commute,
        "commute_basis": basis,
        "coords": map_position(listing.latitude, listing.longitude),
        "lat": listing.latitude,
        "lon": listing.longitude,
        "val": valuation_view(listing, valuation),
        "agent": agent_state(listing, agent_link),
        "thumb": thumb,
        "photos": gallery,
        "source_url": listing.source_url,
        "fetched_at": listing.fetched_at.isoformat() if listing.fetched_at else None,
        "status": getattr(listing.status, "value", listing.status),
    }
