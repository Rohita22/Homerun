"""``/api/ui/*`` — the endpoints the Homerun UI calls, one per screen.

Handlers stay thin: they validate input, call a journey service (which sequences the existing
agents) and return its result. Nothing here knows how ranking, valuation or handoff work.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response

from app.api.deps import (
    get_app_settings,
    get_chat_service,
    get_handoff_ui_service,
    get_match_service,
    get_property_repository,
    get_request_id,
    get_viewing_service,
)
from app.core.config import Settings
from app.journey.chat_service import ChatService
from app.journey.handoff_ui_service import HandoffUiService
from app.journey.match_service import MatchService
from app.journey.viewing_service import ViewingService
from app.journey.views import listing_view
from app.journey.geo import ALL_TOWNS, WORKPLACE_NAME, nearby_towns
from app.providers.listing.factory import get_listing_provider
from app.repositories.property_repository import PropertyRepository
from app.schemas.journey import (
    ChatTurnRequest,
    CompareTurnRequest,
    FeedbackTurnRequest,
    FinanceTurnRequest,
    HandoffTurnRequest,
    InterestRequest,
    MatchRequest,
    PhotoCreate,
    UIProfile,
    ViewingCreate,
    ViewingPatch,
)
from app.services.journey_ranker import DEFAULT_WEIGHTS

router = APIRouter(prefix="/ui", tags=["ui"])


@router.get("/config")
def get_config(
    settings: Settings = Depends(get_app_settings),
    properties: PropertyRepository = Depends(get_property_repository),
) -> dict:
    refreshed = properties.latest_fetched_at("propertyguru_scraper")
    default = UIProfile()
    return {
        "towns": ALL_TOWNS,
        "popular_towns": settings.ui_town_list,
        "nearby": nearby_towns(),
        "defaults": {
            "budget": default.budget, "min_bed": default.min_bed, "types": default.types,
            "towns": default.towns, "weights": dict(DEFAULT_WEIGHTS),
        },
        "workplace": WORKPLACE_NAME,
        "catalog_size": properties.count("propertyguru_scraper", status="active"),
        "refreshed_at": refreshed.isoformat() if refreshed else None,
        "provider": get_listing_provider().name,
        "llm_provider": settings.llm_provider,
        "models": {
            "llm_provider": settings.llm_provider,
            "chat": settings.gemini_model if settings.llm_provider == "gemini" else "template extractor",
            "chat_fallback": settings.gemini_fallback_model if settings.llm_provider == "gemini" else None,
            "voice": settings.gemini_live_model if settings.gemini_api_key else None,
            "voice_name": settings.gemini_live_voice,
            "voice_configured": bool(settings.gemini_api_key),
        },
        "vision_available": bool(settings.gemini_api_key),
    }


@router.post("/chat")
def post_chat(
    body: ChatTurnRequest,
    request_id: str = Depends(get_request_id),
    service: ChatService = Depends(get_chat_service),
) -> dict:
    return service.turn(request_id, body.session_id, body.message, body.profile, body.restart)


@router.post("/match")
def post_match(
    body: MatchRequest,
    request_id: str = Depends(get_request_id),
    service: MatchService = Depends(get_match_service),
) -> dict:
    return service.match(request_id, body.session_id, body.profile, body.limit)


@router.post("/feedback")
def post_feedback(
    body: FeedbackTurnRequest,
    request_id: str = Depends(get_request_id),
    service: MatchService = Depends(get_match_service),
) -> dict:
    return service.feedback(request_id, body)


@router.post("/finance")
def post_finance(
    body: FinanceTurnRequest,
    request_id: str = Depends(get_request_id),
    service: MatchService = Depends(get_match_service),
) -> dict:
    return service.finance(request_id, body.listing_id, body.down_payment_pct, body.annual_rate_pct, body.years)


@router.post("/compare")
def post_compare(
    body: CompareTurnRequest,
    request_id: str = Depends(get_request_id),
    service: MatchService = Depends(get_match_service),
) -> dict:
    return service.compare(request_id, body.ids, body.down_payment_pct, body.annual_rate_pct, body.years)


_ONEMAP = "https://www.onemap.gov.sg/api/common/elastic/search"


def _onemap_places(q: str) -> list[dict]:
    """Named places (condos, HDB blocks, streets) from OneMap's public search; [] if it is down."""
    import httpx

    try:
        r = httpx.get(_ONEMAP, params={"searchVal": q, "returnGeom": "Y", "getAddrDetails": "Y"}, timeout=4.0)
        r.raise_for_status()
        out = []
        for it in r.json().get("results", [])[:5]:
            lat, lon = float(it["LATITUDE"]), float(it["LONGITUDE"])
            name = it.get("BUILDING") if it.get("BUILDING") not in (None, "NIL") else it.get("ADDRESS")
            out.append({"name": (name or "").title(), "address": (it.get("ADDRESS") or "").title(), "lat": lat, "lon": lon})
        return out
    except Exception:  # noqa: BLE001 - search is best effort
        return []


@router.get("/search")
def search_places(
    q: str = Query(min_length=2, max_length=80),
    properties: PropertyRepository = Depends(get_property_repository),
) -> dict:
    """Find listings by condo / HDB name (catalog) plus matching real-world places (OneMap) for the map."""
    needle = " ".join(q.lower().split())
    hits = []
    for l in properties.list_all("propertyguru_scraper", status="active"):
        view = listing_view(l, properties.get_agent_link(l.listing_id))
        hay = f"{view['name']} {l.address_public or ''}".lower()
        if needle in hay and view["lat"] is not None:
            hits.append((0 if view["name"].lower().startswith(needle) else 1, view))
    hits.sort(key=lambda h: h[0])
    return {"query": q, "listings": [v for _, v in hits[:10]], "places": _onemap_places(q)}


@router.get("/listings")
def get_listings(
    ids: str = Query(description="comma separated listing ids"),
    properties: PropertyRepository = Depends(get_property_repository),
) -> dict:
    wanted = [i for i in ids.split(",") if i][:50]
    return {
        "listings": {
            l.listing_id: listing_view(l, properties.get_agent_link(l.listing_id))
            for l in properties.get_by_ids(wanted)
        }
    }


@router.post("/interest")
def post_interest(
    body: InterestRequest, service: HandoffUiService = Depends(get_handoff_ui_service)
) -> dict:
    return service.interest(body.listing_id)


@router.post("/handoff")
def post_handoff(
    body: HandoffTurnRequest, service: HandoffUiService = Depends(get_handoff_ui_service)
) -> dict:
    return service.submit(body.session_id, body.listing_id, body.channel, body.consent, body.fields)


@router.get("/hub")
def get_hub(session_id: str, service: ViewingService = Depends(get_viewing_service)) -> dict:
    return service.hub(session_id)


@router.post("/viewings")
def create_viewing(body: ViewingCreate, service: ViewingService = Depends(get_viewing_service)) -> dict:
    return service.create(body)


@router.patch("/viewings/{viewing_id}")
def patch_viewing(
    viewing_id: str, body: ViewingPatch, session_id: str,
    service: ViewingService = Depends(get_viewing_service),
) -> dict:
    return service.patch(session_id, viewing_id, body)


@router.delete("/viewings/{viewing_id}", status_code=204, response_class=Response, response_model=None)
def delete_viewing(
    viewing_id: str, session_id: str, service: ViewingService = Depends(get_viewing_service)
) -> None:
    service.delete(session_id, viewing_id)


@router.post("/viewings/{viewing_id}/photos")
def add_photo(
    viewing_id: str, body: PhotoCreate, session_id: str,
    service: ViewingService = Depends(get_viewing_service),
) -> dict:
    return service.add_photo(session_id, viewing_id, body.image_data_url)


@router.post("/viewings/{viewing_id}/photos/{photo_id}/analyze")
def analyze_photo(
    viewing_id: str, photo_id: str, session_id: str,
    service: ViewingService = Depends(get_viewing_service),
) -> dict:
    return service.analyze_photo(session_id, viewing_id, photo_id)


@router.delete("/viewings/{viewing_id}/photos/{photo_id}", status_code=204, response_class=Response, response_model=None)
def delete_photo(
    viewing_id: str, photo_id: str, session_id: str,
    service: ViewingService = Depends(get_viewing_service),
) -> None:
    service.remove_photo(session_id, viewing_id, photo_id)
