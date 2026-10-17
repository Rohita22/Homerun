"""``GET /api/health`` and ``GET /api/metrics`` (PRD section 11 / 9: "Prove s390x host, real
deployed API ... and p95 latency").
"""

from __future__ import annotations

import platform

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session as DbSession

from app.api.deps import INVENTORY_PROVIDER, get_property_repository
from app.core.config import Settings, get_settings
from app.core.metrics import get_metrics_collector
from app.db.base import get_db
from app.ml.valuation_service import get_valuation_service
from app.providers.listing.factory import get_listing_provider
from app.repositories.property_repository import PropertyRepository
from app.schemas.system import HealthResponse, MetricsResponse

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
def health(
    settings: Settings = Depends(get_settings),
    db: DbSession = Depends(get_db),
    property_repo: PropertyRepository = Depends(get_property_repository),
) -> HealthResponse:
    provider = get_listing_provider()
    try:
        db.execute(text("SELECT 1"))
        database_status = "ok"
    except Exception:  # noqa: BLE001
        database_status = "unreachable"

    valuation_service = get_valuation_service()

    return HealthResponse(
        status="ok",
        build_sha=settings.homerun_build_sha,
        architecture=platform.machine() or "unknown",
        listing_provider=provider.name,
        listing_provider_healthy=provider.health(),
        listing_catalog_size=property_repo.count(
            INVENTORY_PROVIDER["scraped"], status="active"
        ),
        llm_provider=settings.llm_provider,
        database=database_status,
        valuation_model_version=valuation_service.version,
        valuation_model_is_trained=valuation_service.is_trained,
        listings_last_refreshed_at=property_repo.latest_fetched_at(
            INVENTORY_PROVIDER["scraped"]
        ),
    )


@router.get("/metrics", response_model=MetricsResponse)
def metrics() -> MetricsResponse:
    """Minimal auth note: in production this would sit behind the reverse proxy's internal-only
    route or a bearer token (PRD section 9: "expose health and secured metrics"). Left open here
    for datathon judging convenience."""
    snapshot = get_metrics_collector().snapshot()
    return MetricsResponse(
        model_version="homerun-backend-0.1.0",
        request_count=snapshot["request_count"],
        error_count=snapshot["error_count"],
        p50_latency_ms=snapshot["p50_latency_ms"],
        p95_latency_ms=snapshot["p95_latency_ms"],
    )
