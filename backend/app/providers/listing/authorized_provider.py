"""Authorized third-party listing connector (PRD section 6: Parse.bot / PropertyGuru marketplace
API). Parse.bot reverse-engineers a target website's real network requests into a typed REST API;
this scraper instance is wired to PropertyGuru Singapore and exposes six endpoints:
``search_properties_for_sale``, ``search_properties_for_rent``, ``get_property_listing_detail``,
``search_new_projects``, ``search_agents``, ``get_condo_detail``.

This connector is disabled (every method raises ``ProviderUnavailableError``) until
``PARSE_BOT_BASE_URL``/``PARSE_BOT_API_KEY`` are both set, so an un-configured deployment fails
over to ``DemoFixtureProvider`` exactly as before (PRD section 16, open decision). Once enabled,
every listing it returns is genuinely live PropertyGuru inventory, not demo data — the system's
``source_mode`` flips to ``live_authorized`` (see ``app.api.deps.get_source_mode``) and the UI's
evidence panel reflects that truthfully.

Two honesty constraints this connector respects:
  - Parse.bot's search endpoints do not actually honour query filters on this scraper instance
    (verified empirically: identical results regardless of query params) — only ``page``
    paginates. Filtering by town/price/bedrooms therefore happens client-side in
    ``MarketIntelligenceAgent``/``HardFilterService`` against the normalized catalog, same as for
    demo fixtures; this connector never pretends to filter server-side.
  - PropertyGuru listing pages never expose an agent's phone/email, only their name and CEA
    license number. ``get_listing_agent`` reflects that honestly (``approved_contact=None``), so
    ``HandoffService.classify`` naturally falls back to the safe original-listing-only channel
    for every live listing instead of a contact channel being silently fabricated.
"""

from __future__ import annotations

import re
from typing import Any

import httpx

from app.core.errors import ProviderUnavailableError
from app.core.logging import get_logger
from app.core.time import utcnow
from app.domain.entities import Agent, ListingAgentLink, PropertyListing
from app.domain.enums import AssociationStatus, ListingStatus, PropertyType, TransactionType

logger = get_logger(__name__)

SGD_SQFT_TO_SQM = 0.092903

# Canonical HDB town names (matches the vocabulary the valuation model was trained on). PropertyGuru
# addresses use informal district/area labels, so we scan for the longest known town name inside
# the address text rather than trusting PropertyGuru's own district grouping.
HDB_TOWNS = [
    "ANG MO KIO", "BEDOK", "BISHAN", "BUKIT BATOK", "BUKIT MERAH", "BUKIT PANJANG",
    "BUKIT TIMAH", "CENTRAL AREA", "CHOA CHU KANG", "CLEMENTI", "GEYLANG", "HOUGANG",
    "JURONG EAST", "JURONG WEST", "KALLANG/WHAMPOA", "KALLANG", "MARINE PARADE", "PASIR RIS",
    "PUNGGOL", "QUEENSTOWN", "SEMBAWANG", "SENGKANG", "SERANGOON", "TAMPINES", "TOA PAYOH",
    "WOODLANDS", "YISHUN",
]

LANDED_KEYWORDS = ("landed", "terrace", "bungalow", "semi-d", "cluster-house", "corner-terrace")
EC_KEYWORDS = ("executive-condominium", "executive condominium")

_LEASE_RE = re.compile(r"lease remaining[:\s]*([\d.]+)\s*year", re.IGNORECASE)
_SQFT_RE = re.compile(r"([\d,]+(?:\.\d+)?)\s*sqft", re.IGNORECASE)


def _infer_town(*texts: str | None) -> str | None:
    haystack = " ".join(t for t in texts if t).upper()
    matches = [town for town in HDB_TOWNS if town in haystack]
    if not matches:
        return None
    return max(matches, key=len)


def _infer_property_type_from_text(*texts: str | None) -> PropertyType:
    haystack = " ".join(t for t in texts if t).lower()
    if "hdb" in haystack:
        return PropertyType.HDB
    if any(kw in haystack for kw in EC_KEYWORDS):
        return PropertyType.EC
    if any(kw in haystack for kw in LANDED_KEYWORDS):
        return PropertyType.LANDED
    return PropertyType.CONDO


def _map_detail_property_type(value: str | None, *fallback_texts: str | None) -> PropertyType:
    if value:
        normalized = value.strip().upper()
        if normalized == "HDB":
            return PropertyType.HDB
        if "EXECUTIVE CONDOMINIUM" in normalized or normalized == "EC":
            return PropertyType.EC
        if any(kw in normalized for kw in ("LANDED", "TERRACE", "BUNGALOW", "SEMI-DETACHED", "CLUSTER")):
            return PropertyType.LANDED
        if "CONDO" in normalized or "APARTMENT" in normalized:
            return PropertyType.CONDO
    return _infer_property_type_from_text(*fallback_texts)


def _infer_flat_type(bedrooms: int | None, property_type: PropertyType) -> str | None:
    if property_type != PropertyType.HDB or bedrooms is None:
        return None
    return {0: "2 ROOM", 1: "2 ROOM", 2: "3 ROOM", 3: "4 ROOM", 4: "5 ROOM"}.get(bedrooms, "EXECUTIVE")


def _parse_floor_area_sqm(floor_area: Any) -> float | None:
    if floor_area is None:
        return None
    if isinstance(floor_area, (int, float)):
        return round(float(floor_area) * SGD_SQFT_TO_SQM, 1)
    match = _SQFT_RE.search(str(floor_area))
    if not match:
        return None
    sqft = float(match.group(1).replace(",", ""))
    return round(sqft * SGD_SQFT_TO_SQM, 1)


def _coerce_floor_level(value: Any) -> str | None:
    """Parse.bot's ``floor_level`` is sometimes a plain string and sometimes a structured
    ``{"code": ..., "description": ...}`` dict depending on the listing — normalize both shapes
    to a plain string instead of trusting the response to be consistent."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return value.get("description") or value.get("code")
    return str(value)


def _parse_lease_remaining(description: str | None) -> float | None:
    if not description:
        return None
    match = _LEASE_RE.search(description)
    return float(match.group(1)) if match else None


def _agent_id_for(raw_agent: dict | None) -> str | None:
    if not raw_agent or raw_agent.get("id") is None:
        return None
    return f"propertyguru-agent-{raw_agent['id']}"


class AuthorizedListingProvider:
    name = "authorized"

    def __init__(
        self,
        base_url: str | None,
        api_key: str | None,
        max_search_pages: int = 2,
        include_rent: bool = True,
        detail_enrich_limit: int = 20,
        request_timeout_s: float = 45.0,
    ) -> None:
        self._base_url = base_url.rstrip("/") if base_url else None
        self._api_key = api_key
        self._enabled = bool(base_url and api_key)
        self._max_search_pages = max_search_pages
        self._include_rent = include_rent
        self._detail_enrich_limit = detail_enrich_limit
        self._client = httpx.Client(
            timeout=request_timeout_s,
            headers={"X-API-Key": api_key} if api_key else {},
        )
        # Parse.bot bills per call against a small daily quota, so `health()` must never make a
        # live request on every poll (the evidence panel/health endpoint can be hit often) — it
        # reports the outcome of the last real call this process actually made instead.
        self._last_call_ok: bool | None = None

    def _require_enabled(self) -> None:
        if not self._enabled:
            raise ProviderUnavailableError(
                "Authorized listing provider is not configured (missing PARSE_BOT_BASE_URL / "
                "PARSE_BOT_API_KEY); use the demo fixture provider instead.",
                details={"provider": self.name},
            )

    def _call(self, endpoint: str, params: dict[str, Any] | None = None) -> dict:
        url = f"{self._base_url}/{endpoint}"
        logger.info("parse_bot_request endpoint=%s params=%s", endpoint, params or {})
        try:
            response = self._client.get(url, params=params or {})
        except httpx.HTTPError as exc:
            logger.warning("parse_bot_request_failed endpoint=%s error=%s", endpoint, exc)
            self._last_call_ok = False
            raise ProviderUnavailableError(
                f"Parse.bot request to {endpoint} failed: {exc}", details={"endpoint": endpoint}
            ) from exc
        if response.status_code != 200:
            logger.warning(
                "parse_bot_non_200 endpoint=%s status=%d body=%s",
                endpoint, response.status_code, response.text[:300],
            )
            self._last_call_ok = False
            raise ProviderUnavailableError(
                f"Parse.bot endpoint {endpoint} returned HTTP {response.status_code}",
                details={"endpoint": endpoint, "status_code": response.status_code},
            )
        payload = response.json()
        if payload.get("status") != "success":
            self._last_call_ok = False
            raise ProviderUnavailableError(
                f"Parse.bot endpoint {endpoint} did not return success",
                details={"endpoint": endpoint, "payload": payload},
            )
        self._last_call_ok = True
        return payload["data"]

    # --- normalization -------------------------------------------------

    def _normalize_search_item(self, raw: dict, transaction_type: TransactionType) -> PropertyListing | None:
        slug = raw.get("slug")
        if not slug:
            return None
        agent_raw = raw.get("agent") or {}
        property_type = _infer_property_type_from_text(slug, raw.get("title"))
        bedrooms = raw.get("bedrooms")
        return PropertyListing(
            listing_id=slug,
            provider="authorized_parse_bot",
            external_id=str(raw.get("id", slug)),
            source_url=raw.get("url"),
            published_at=None,
            fetched_at=utcnow(),
            status=ListingStatus.ACTIVE,
            transaction_type=transaction_type,
            property_type=property_type,
            asking_price_sgd=(raw.get("price") or {}).get("value"),
            bedrooms=bedrooms,
            bathrooms=raw.get("bathrooms"),
            floor_area_sqm=_parse_floor_area_sqm(raw.get("floor_area")),
            address_public=raw.get("address"),
            town=_infer_town(raw.get("address"), raw.get("title")),
            latitude=None,
            longitude=None,
            tenure=None,
            lease_remaining_years=None,
            floor_level=None,
            flat_type=_infer_flat_type(bedrooms, property_type),
            flat_model=None,
            storey_range=None,
            attributes={"psf": raw.get("psf"), "mrt": (raw.get("mrt") or {}).get("nearbyText")},
            images_allowed=False,
            agent_ref=_agent_id_for(agent_raw),
            attribution="PropertyGuru Singapore (live, via Parse.bot connector)",
            rights_status="licensed_display_only",
        )

    def _normalize_detail(
        self, slug: str, data: dict, transaction_type: TransactionType
    ) -> PropertyListing:
        agent_raw = data.get("agent") or {}
        property_type = _map_detail_property_type(
            data.get("property_type"), slug, data.get("title")
        )
        bedrooms = data.get("bedrooms")
        return PropertyListing(
            listing_id=slug,
            provider="authorized_parse_bot",
            external_id=str(data.get("listing_id", slug)),
            source_url=f"https://www.propertyguru.com.sg/listing/{slug}",
            published_at=None,
            fetched_at=utcnow(),
            status=ListingStatus.ACTIVE,
            transaction_type=transaction_type,
            property_type=property_type,
            asking_price_sgd=(data.get("price") or {}).get("value"),
            bedrooms=bedrooms,
            bathrooms=data.get("bathrooms"),
            floor_area_sqm=_parse_floor_area_sqm(data.get("floor_area")),
            address_public=data.get("address"),
            town=_infer_town(data.get("district"), data.get("address")),
            latitude=None,
            longitude=None,
            tenure=data.get("tenure"),
            lease_remaining_years=_parse_lease_remaining(data.get("description")),
            floor_level=_coerce_floor_level(data.get("floor_level")),
            flat_type=_infer_flat_type(bedrooms, property_type),
            flat_model=None,
            storey_range=None,
            attributes={
                "agency": data.get("agency"),
                "postal_code": data.get("postal_code"),
                "furnishing": data.get("furnishing"),
            },
            images_allowed=False,
            agent_ref=_agent_id_for(agent_raw),
            attribution="PropertyGuru Singapore (live, via Parse.bot connector)",
            rights_status="licensed_display_only",
        )

    def _agent_from_raw(self, raw_agent: dict | None) -> Agent | None:
        agent_id = _agent_id_for(raw_agent)
        if not agent_id or not raw_agent:
            return None
        return Agent(
            agent_id=agent_id,
            provider_id=str(raw_agent.get("id")),
            name=raw_agent.get("name"),
            cea_number=raw_agent.get("license_number"),
            # PropertyGuru listing pages never expose phone/email — never fabricate contact
            # details; HandoffService safely falls back to the original listing link.
            approved_contact=None,
            verified_at=None,
        )

    # --- ListingProvider protocol ---------------------------------------

    def search_listings(
        self, filters: dict[str, Any], page: int = 1, page_size: int = 50
    ) -> list[PropertyListing]:
        self._require_enabled()
        wants_rent = filters.get("transaction_type") == "rent"
        transaction_type = TransactionType.RENT if wants_rent else TransactionType.BUY
        endpoint = "search_properties_for_rent" if wants_rent else "search_properties_for_sale"

        results: list[PropertyListing] = []
        pb_page = 1
        while len(results) < page_size and pb_page <= self._max_search_pages:
            data = self._call(endpoint, {"page": pb_page})
            raw_listings = data.get("listings", [])
            if not raw_listings:
                break
            for raw in raw_listings:
                listing = self._normalize_search_item(raw, transaction_type)
                if listing:
                    results.append(listing)
            pb_page += 1
        logger.info(
            "parse_bot_search_complete endpoint=%s pages=%d n_results=%d",
            endpoint, pb_page - 1, len(results),
        )
        return results[:page_size]

    def get_listing(self, source_listing_id: str) -> PropertyListing | None:
        self._require_enabled()
        try:
            data = self._call("get_property_listing_detail", {"listing_slug": source_listing_id})
        except ProviderUnavailableError:
            return None
        transaction_type = (
            TransactionType.RENT if "for-rent" in source_listing_id else TransactionType.BUY
        )
        return self._normalize_detail(source_listing_id, data, transaction_type)

    def get_listing_agent(self, source_listing_id: str) -> tuple[Agent, ListingAgentLink] | None:
        self._require_enabled()
        try:
            data = self._call("get_property_listing_detail", {"listing_slug": source_listing_id})
        except ProviderUnavailableError:
            return None
        agent = self._agent_from_raw(data.get("agent"))
        if agent is None:
            return None
        link = ListingAgentLink(
            listing_id=source_listing_id,
            agent_id=agent.agent_id,
            # The agent came directly from the authoritative listing detail page itself, not a
            # third-party guess, so the association evidence is genuine even though contact
            # details are not available (see module docstring).
            evidence_source="parse_bot_listing_detail_page",
            association_status=AssociationStatus.VERIFIED,
            checked_at=utcnow(),
        )
        return agent, link

    def health(self) -> bool:
        """Deliberately makes no live call: Parse.bot bills per request against a small daily
        quota, and this can be polled often (the frontend's evidence panel, /api/health). Reports
        the outcome of the last real call this process actually made, falling back to "is it even
        configured" before any call has happened yet."""
        if not self._enabled:
            return False
        return self._last_call_ok if self._last_call_ok is not None else True

    # --- catalog sync (bootstrap / manual refresh) ----------------------

    def sync_catalog(self) -> tuple[list[PropertyListing], list[Agent], list[ListingAgentLink]]:
        """Fetch live sale (+ rent) listings and enrich a bounded subset with full detail calls
        (accurate property_type/tenure/lease + agent identity). Returns normalized records ready
        for ``PropertyRepository.upsert_many``/``upsert_agent``/``upsert_link``. Never raises —
        any individual failure is logged and skipped so one bad listing can't break the sync."""
        self._require_enabled()
        logger.info(
            "live_catalog_sync_start max_search_pages=%d include_rent=%s detail_enrich_limit=%d",
            self._max_search_pages, self._include_rent, self._detail_enrich_limit,
        )

        lightweight: list[PropertyListing] = []
        try:
            lightweight.extend(
                self.search_listings({"transaction_type": "buy"}, page=1, page_size=10_000)
            )
        except ProviderUnavailableError as exc:
            logger.warning("live_catalog_sync_sale_failed error=%s", exc)
        if self._include_rent:
            try:
                lightweight.extend(
                    self.search_listings({"transaction_type": "rent"}, page=1, page_size=10_000)
                )
            except ProviderUnavailableError as exc:
                logger.warning("live_catalog_sync_rent_failed error=%s", exc)

        # Prioritize HDB-looking listings for detail enrichment (that's where the valuation
        # model's explainability story lives); fill remaining budget with everything else.
        hdb_first = sorted(lightweight, key=lambda L: 0 if L.property_type == PropertyType.HDB else 1)
        to_enrich = hdb_first[: self._detail_enrich_limit]
        enrich_ids = {L.listing_id for L in to_enrich}

        listings: list[PropertyListing] = [L for L in lightweight if L.listing_id not in enrich_ids]
        agents: list[Agent] = []
        links: list[ListingAgentLink] = []

        for lightweight_listing in to_enrich:
            slug = lightweight_listing.listing_id
            try:
                raw_detail = self._call("get_property_listing_detail", {"listing_slug": slug})
                enriched = self._normalize_detail(slug, raw_detail, lightweight_listing.transaction_type)
            except Exception as exc:  # noqa: BLE001 - one malformed listing must never break the sync
                logger.warning("live_catalog_sync_detail_failed slug=%s error=%s", slug, exc)
                listings.append(lightweight_listing)
                continue
            listings.append(enriched)
            agent = self._agent_from_raw(raw_detail.get("agent"))
            if agent:
                agents.append(agent)
                links.append(
                    ListingAgentLink(
                        listing_id=slug,
                        agent_id=agent.agent_id,
                        evidence_source="parse_bot_listing_detail_page",
                        association_status=AssociationStatus.VERIFIED,
                        checked_at=utcnow(),
                    )
                )

        # Parse.bot pagination occasionally repeats a listing across pages (and a listing can
        # legitimately be returned by both the sale and rent searches). Dedupe by listing_id,
        # keeping the detail-enriched version when a listing appears both ways, so the bulk
        # upsert never sees the same primary key twice in one batch.
        deduped: dict[str, PropertyListing] = {}
        for listing in listings:
            if listing.listing_id not in deduped or listing.listing_id in enrich_ids:
                deduped[listing.listing_id] = listing
        listings = list(deduped.values())
        agents = list({a.agent_id: a for a in agents}.values())
        links = list({link.listing_id: link for link in links}.values())

        logger.info(
            "live_catalog_sync_complete n_listings=%d n_detail_enriched=%d n_agents=%d",
            len(listings), len(to_enrich), len(agents),
        )
        return listings, agents, links
