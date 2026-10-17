"""PRD section 7C/14: trained model beats the comparable-sales median baseline, reports
coverage, and never scores condos."""

from __future__ import annotations

import tempfile
from pathlib import Path

from app.domain.entities import PropertyListing
from app.domain.enums import ValuationStatus
from app.ml.train import train
from app.ml.valuation_service import ValuationService


def test_trained_model_beats_baseline_and_reports_coverage() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        metrics = train(out_dir=Path(tmp), synthetic_n=1200)
        assert metrics["beats_baseline"] is True
        assert 0.0 <= metrics["hgb_test_metrics"]["interval_empirical_coverage"] <= 1.0
        assert metrics["is_synthetic_training_data"] is True


def test_valuation_service_predicts_for_hdb_with_artifact() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        train(out_dir=Path(tmp), synthetic_n=1200)
        service = ValuationService(artifacts_dir=Path(tmp))

        listing = PropertyListing.model_validate(
            {
                "listing_id": "x1", "provider": "demo_fixture", "external_id": "x1",
                "fetched_at": "2026-09-01T00:00:00", "status": "active", "transaction_type": "buy",
                "property_type": "HDB", "town": "TAMPINES", "flat_type": "4 ROOM",
                "floor_area_sqm": 92.0, "storey_range": "07 TO 09", "flat_model": "Model A",
                "lease_remaining_years": 70, "attributes": {"transaction_month": "2026-08"},
            }
        )
        result = service.predict(listing)
        assert result.status == ValuationStatus.SUPPORTED_HDB.value
        assert result.point_estimate_sgd > 0
        assert result.interval_low_sgd < result.point_estimate_sgd < result.interval_high_sgd


def test_valuation_unsupported_for_condo() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        service = ValuationService(artifacts_dir=Path(tmp))  # no artifact -> baseline fallback
        listing = PropertyListing.model_validate(
            {
                "listing_id": "c1", "provider": "demo_fixture", "external_id": "c1",
                "fetched_at": "2026-09-01T00:00:00", "status": "active", "transaction_type": "buy",
                "property_type": "CONDO",
            }
        )
        result = service.predict(listing)
        assert result.status == ValuationStatus.UNSUPPORTED_PROPERTY_TYPE.value
        assert result.point_estimate_sgd is None
