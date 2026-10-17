"""Resolve scraped listings to coordinates with OneMap's public search endpoint.

PropertyGuru's search cards carry no coordinates, but the map view and the commute estimate need
them. OneMap (Singapore Land Authority) geocodes an HDB block / condo name without a token. A
result is only accepted when it lands inside Singapore; anything else stays ``None`` so the UI says
"not on map" rather than guessing. Results are written back to ``properties.lat/lon``, which
``PropertyRepository.upsert`` preserves across later scrapes, so each listing is looked up once.
"""

from __future__ import annotations

import re
import time

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.base import SessionLocal
from app.domain.entities import PropertyListing
from app.repositories.property_repository import PropertyRepository

logger = get_logger(__name__)

ONEMAP_SEARCH = "https://www.onemap.gov.sg/api/common/elastic/search"
_SG_LAT = (1.15, 1.50)
_SG_LON = (103.55, 104.10)
_BLOCK_RE = re.compile(r"^\s*(\d+[A-Z]?)\s+(.+)$", re.IGNORECASE)


def _query_for(listing: PropertyListing) -> str | None:
    title = (listing.attributes or {}).get("title") or (listing.address_public or "").split(",")[0]
    title = (title or "").strip()
    return title or None


def _pick(results: list[dict], listing: PropertyListing, query: str) -> tuple[float, float] | None:
    block = _BLOCK_RE.match(query)
    for item in results:
        try:
            lat, lon = float(item["LATITUDE"]), float(item["LONGITUDE"])
        except (KeyError, TypeError, ValueError):
            continue
        if not (_SG_LAT[0] <= lat <= _SG_LAT[1] and _SG_LON[0] <= lon <= _SG_LON[1]):
            continue
        if block and listing.property_type.value == "HDB":  # HDB: the block number must match
            if str(item.get("BLK_NO", "")).upper() != block.group(1).upper():
                continue
        return lat, lon
    return None


class Throttled(RuntimeError):
    """OneMap kept answering 429 after backing off; stop and try again on the next run."""


def geocode_listing(listing: PropertyListing, client: httpx.Client) -> tuple[float, float] | None:
    query = _query_for(listing)
    if not query:
        return None
    for attempt in range(1, 4):
        response = client.get(
            ONEMAP_SEARCH,
            params={"searchVal": query, "returnGeom": "Y", "getAddrDetails": "Y", "pageNum": 1},
        )
        if response.status_code == 429:
            time.sleep(6 * attempt)
            continue
        response.raise_for_status()
        return _pick(response.json().get("results") or [], listing, query)
    raise Throttled(query)


def geocode_missing(provider: str, limit: int = 500, delay_s: float = 1.2) -> dict:
    """Geocode active listings that have no coordinates yet. Never raises; returns a summary."""
    db = SessionLocal()
    done = failed = skipped = 0
    try:
        repo = PropertyRepository(db)
        todo = [
            l for l in repo.list_all(provider, status="active")
            if l.latitude is None or l.longitude is None
        ][:limit]
        token = get_settings().onemap_token
        headers = {"Authorization": token} if token else {}
        with httpx.Client(timeout=10.0, headers=headers) as client:
            for listing in todo:
                try:
                    hit = geocode_listing(listing, client)
                except Throttled:
                    logger.warning("geocode_throttled stopping; will resume on the next run")
                    break
                except (httpx.HTTPError, ValueError) as exc:
                    failed += 1
                    logger.warning("geocode_failed listing=%s error=%s", listing.listing_id, exc)
                    continue
                if hit is None:
                    skipped += 1
                    continue
                repo.set_geo(listing.listing_id, *hit)
                done += 1
                if done % 25 == 0:
                    db.commit()
                time.sleep(delay_s)
        db.commit()
    finally:
        db.close()
    summary = {"geocoded": done, "no_match": skipped, "errors": failed}
    logger.info("geocode_run_complete %s", summary)
    return summary
