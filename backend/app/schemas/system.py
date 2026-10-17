"""Schemas for ``GET /api/health`` and ``GET /api/metrics`` (PRD section 11 / 9 / 13)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    build_sha: str
    architecture: str
    listing_provider: str
    listing_provider_healthy: bool
    listing_catalog_size: int
    llm_provider: str
    database: str
    valuation_model_version: str
    valuation_model_is_trained: bool
    listings_last_refreshed_at: datetime | None = None


class MetricsResponse(BaseModel):
    model_version: str
    request_count: int
    error_count: int
    p50_latency_ms: float
    p95_latency_ms: float
