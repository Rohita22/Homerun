"""FastAPI application factory and entry point.

Run with: ``uvicorn app.main:app --reload`` (dev) or via the systemd unit described in
``scripts/bootstrap.sh`` on the LinuxONE host (PRD section 9: deployment requirements).
"""

from __future__ import annotations

import asyncio
import platform
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import (
    chat,
    compare,
    feedback,
    finance,
    handoffs,
    health,
    preferences,
    properties,
    recommendations,
    voice,
)
from app.bootstrap import bootstrap
from app.core.config import get_settings
from app.core.errors import HomerunError
from app.core.logging import configure_logging, get_logger, log_startup_banner
from app.core.middleware import RequestContextMiddleware
from app.db.base import SessionLocal
from app.ml.valuation_service import get_valuation_service
from app.providers.listing.factory import get_listing_provider
from app.repositories.property_repository import PropertyRepository
from app.scraper.scheduler import scrape_forever

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ANN201, ARG001
    settings = get_settings()
    configure_logging(debug=settings.homerun_debug)
    bootstrap()

    provider = get_listing_provider()
    valuation_service = get_valuation_service()
    db = SessionLocal()
    try:
        catalog_size = len(PropertyRepository(db).list_all())
    finally:
        db.close()

    log_startup_banner(
        {
            "environment": settings.homerun_env,
            "architecture (uname -m)": platform.machine() or "unknown",
            "listing provider": f"{provider.name} (healthy={provider.health()})",
            "listing catalog size": catalog_size,
            "llm provider": settings.llm_provider,
            "valuation model": (
                f"{valuation_service.version} "
                f"({'trained' if valuation_service.is_trained else 'baseline fallback'})"
            ),
            "build sha": settings.homerun_build_sha,
        }
    )
    scrape_task = None
    if settings.listing_provider == "scraped" and settings.scrape_enabled:
        scrape_task = asyncio.create_task(scrape_forever(settings), name="propertyguru-scraper")
    yield
    if scrape_task is not None:
        scrape_task.cancel()
    logger.info("homerun_backend_shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Homerun API",
        description=(
            "Explainable, multi-agent Singapore property discovery backend "
            "(IBM Z Datathon 2026). See PRD section 11 for the full API contract."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(HomerunError)
    async def homerun_error_handler(request: Request, exc: HomerunError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "req-unknown")
        logger.warning(
            "request_failed code=%s path=%s request_id=%s message=%s",
            exc.code, request.url.path, request_id, exc.message,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "request_id": request_id,
                    "details": exc.details,
                }
            },
        )

    api_routers = [
        health.router,
        chat.router,
        preferences.router,
        recommendations.router,
        properties.router,
        compare.router,
        feedback.router,
        finance.router,
        handoffs.router,
        voice.router,
    ]
    for router in api_routers:
        app.include_router(router, prefix="/api")

    return app


app = create_app()
