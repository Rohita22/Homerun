"""Concrete ``ValuationModel`` used by the Valuation agent.

Prefers a trained :class:`HDBValuationArtifact` (point estimate + calibrated interval) when one
has been produced by ``app.ml.train``; otherwise falls back to the comparable-sales median
baseline fit on the same (synthetic-by-default) reference dataset, so the API never hard-fails
just because nobody has run the training script yet. Only HDB is ever supported, per PRD section
7C ("For condo listings return 'estimate unavailable' until an independently validated
private-property model exists").
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd

from app.core.config import get_settings
from app.core.logging import get_logger
from app.domain.entities import PropertyListing, ValuationResult
from app.domain.enums import PropertyType, ValuationStatus
from app.ml.baseline_model import ComparableSalesMedianModel
from app.ml.features import listing_to_feature_row, prepare_training_frame
from app.ml.hgb_model import HDBValuationArtifact
from app.ml.train import MODEL_FILENAME, _synthetic_dataset

logger = get_logger(__name__)


class ValuationService:
    def __init__(self, artifacts_dir: Path) -> None:
        self._artifacts_dir = artifacts_dir
        self._artifact: HDBValuationArtifact | None = self._try_load_artifact()
        self._baseline: ComparableSalesMedianModel | None = None
        self._baseline_is_synthetic = True
        if self._artifact is None:
            self._baseline = self._fit_fallback_baseline()
        self.version = self._artifact.version if self._artifact else self._baseline.version

    def _try_load_artifact(self) -> HDBValuationArtifact | None:
        path = self._artifacts_dir / MODEL_FILENAME
        if not path.exists():
            return None
        try:
            return HDBValuationArtifact.load(path)
        except Exception as exc:  # noqa: BLE001 - any load failure must degrade, never crash
            logger.warning("valuation_artifact_load_failed path=%s error=%s", path, exc)
            return None

    def _fit_fallback_baseline(self) -> ComparableSalesMedianModel:
        logger.info(
            "No trained valuation artifact found; fitting comparable-sales median baseline on "
            "synthetic bootstrap data. Run `python -m app.ml.train --data-path <data.gov.sg csv>`"
            " for a real trained model."
        )
        df = prepare_training_frame(_synthetic_dataset())
        return ComparableSalesMedianModel().fit(df)

    @property
    def is_trained(self) -> bool:
        return self._artifact is not None

    def is_supported(self, listing: PropertyListing) -> bool:
        prop_type = listing.property_type
        prop_type_value = prop_type.value if hasattr(prop_type, "value") else prop_type
        return prop_type_value == PropertyType.HDB.value

    def predict(self, listing: PropertyListing) -> ValuationResult:
        if not self.is_supported(listing):
            return ValuationResult(
                status=ValuationStatus.UNSUPPORTED_PROPERTY_TYPE.value,
                reason=(
                    "HDB-only valuation model (PRD scope); no validated model exists for this "
                    "property type yet."
                ),
            )

        row = listing_to_feature_row(listing)
        if row["floor_area_sqm"] is None or row["transaction_month"] is None:
            row = {**row, "transaction_month": row["transaction_month"] or "2026-09"}
        if row["floor_area_sqm"] is None:
            return ValuationResult(
                status=ValuationStatus.INSUFFICIENT_FEATURES.value,
                reason="Missing floor area; cannot compute a valuation estimate.",
            )
        row["transaction_month_ordinal"] = _month_ordinal(row["transaction_month"])

        if self._artifact is not None:
            df = pd.DataFrame([row])
            point, low, high = self._artifact.predict_with_interval(df)
            return ValuationResult(
                status=ValuationStatus.SUPPORTED_HDB.value,
                point_estimate_sgd=round(float(point[0]), -2),
                interval_low_sgd=round(float(low[0]), -2),
                interval_high_sgd=round(float(high[0]), -2),
                coverage_note=(
                    f"Conformalized {int(self._artifact.calibration.nominal_coverage * 100)}% "
                    "quantile-regression interval, calibrated on held-out validation months; "
                    "see hdb_valuation_metrics.json for the measured empirical coverage on the "
                    "untouched test period — tree-based models can't extrapolate price drift "
                    "past the training window, so real coverage degrades the further out you go."
                ),
                model_version=self._artifact.version,
            )

        point = self._baseline.predict_one(row["town"], row["flat_type"])
        if point is None:
            return ValuationResult(
                status=ValuationStatus.MODEL_UNAVAILABLE.value,
                reason="No comparable-sales data available for this town/flat type combination.",
            )
        return ValuationResult(
            status=ValuationStatus.SUPPORTED_HDB.value,
            point_estimate_sgd=round(point, -2),
            interval_low_sgd=round(point * 0.92, -2),
            interval_high_sgd=round(point * 1.08, -2),
            coverage_note=(
                "Baseline comparable-sales median only (no trained model artifact found); "
                "interval is an unvalidated +/-8% heuristic, not an empirical guarantee."
            ),
            model_version=self._baseline.version,
        )


def _month_ordinal(month_str: str) -> int:
    from app.ml.features import month_to_ordinal

    return month_to_ordinal(month_str) or 0


@lru_cache
def get_valuation_service() -> ValuationService:
    return ValuationService(artifacts_dir=get_settings().ml_artifacts_dir)
