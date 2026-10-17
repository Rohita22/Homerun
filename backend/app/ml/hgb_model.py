"""Trained HDB resale valuation model: three sklearn ``HistGradientBoostingRegressor`` pipelines
over the shared feature schema — a point estimate (squared-error loss) plus a lower/upper
conditional-quantile pair — combined with a conformalized-quantile-regression (CQR) correction
fit on held-out validation data.

Why CQR instead of a flat residual shift: a constant-width interval (point +/- same offset for
every listing) assumes uncertainty is the same for a common 4-room Tampines flat as for a rare
Executive flat in a thin market, which is false. Quantile regression lets the lower/upper models
learn *conditional* quantiles (interval width can vary by town/flat_type/floor area), and CQR
(Romano, Patterson & Candes, 2019) adds a single scalar margin from validation conformity scores
so the interval keeps a distribution-free finite-sample coverage guarantee even though the
underlying quantile models are themselves just approximations (PRD section 7C: "report interval
empirical coverage and width on untouched test months").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder

from app.ml.features import CATEGORICAL_COLUMNS, NUMERIC_COLUMNS, TARGET_COLUMN


@dataclass
class CalibrationResult:
    """Conformalized-quantile-regression margin from a held-out validation split. Market drift
    weakens this guarantee over time (PRD 7C), which is why ``fitted_on_months`` is recorded and
    surfaced in the API response as a caveat."""

    conformal_margin: float
    nominal_coverage: float = 0.80
    fitted_on_months: list[int] = field(default_factory=list)

    # Back-compat aliases for any artifact saved before the CQR rewrite.
    lower_residual_quantile: float = 0.0
    upper_residual_quantile: float = 0.0


class HDBValuationArtifact:
    """Bundles all three fitted pipelines + the CQR calibration so they can never drift apart (a
    point model without its quantile models, or either without its conformal margin, would
    silently report wrong intervals)."""

    version: str

    def __init__(
        self,
        pipeline: Pipeline,
        calibration: CalibrationResult,
        version: str,
        pipeline_low: Pipeline | None = None,
        pipeline_high: Pipeline | None = None,
        feature_importances: dict[str, float] | None = None,
    ) -> None:
        self.pipeline = pipeline
        self.pipeline_low = pipeline_low
        self.pipeline_high = pipeline_high
        self.calibration = calibration
        self.version = version
        self.feature_importances = feature_importances or {}

    @staticmethod
    def build_pipeline(
        random_state: int = 42,
        loss: str = "squared_error",
        quantile: float | None = None,
        max_depth: int | None = 8,
        learning_rate: float = 0.08,
        max_iter: int = 300,
        l2_regularization: float = 0.1,
        min_samples_leaf: int = 20,
    ) -> Pipeline:
        categorical_idx = list(range(len(CATEGORICAL_COLUMNS)))
        preprocessor = ColumnTransformer(
            transformers=[
                (
                    "categorical",
                    OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1),
                    CATEGORICAL_COLUMNS,
                ),
                ("numeric", "passthrough", NUMERIC_COLUMNS),
            ]
        )
        model_kwargs = dict(
            categorical_features=categorical_idx,
            random_state=random_state,
            max_depth=max_depth,
            learning_rate=learning_rate,
            max_iter=max_iter,
            l2_regularization=l2_regularization,
            min_samples_leaf=min_samples_leaf,
            loss=loss,
        )
        if loss == "quantile":
            model_kwargs["quantile"] = quantile
        model = HistGradientBoostingRegressor(**model_kwargs)
        return Pipeline(steps=[("preprocess", preprocessor), ("model", model)])

    def predict_point(self, df: pd.DataFrame) -> np.ndarray:
        cols = CATEGORICAL_COLUMNS + NUMERIC_COLUMNS
        return self.pipeline.predict(df[cols])

    def predict_with_interval(self, df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        cols = CATEGORICAL_COLUMNS + NUMERIC_COLUMNS
        point = self.pipeline.predict(df[cols])
        if self.pipeline_low is not None and self.pipeline_high is not None:
            low = self.pipeline_low.predict(df[cols]) - self.calibration.conformal_margin
            high = self.pipeline_high.predict(df[cols]) + self.calibration.conformal_margin
            # Quantile crossing can happen on out-of-distribution rows; the point estimate must
            # always sit inside its own interval, never outside it.
            low = np.minimum(low, point)
            high = np.maximum(high, point)
        else:
            low = point + self.calibration.lower_residual_quantile
            high = point + self.calibration.upper_residual_quantile
        return point, low, high

    def save(self, path: Path) -> None:
        joblib.dump(self, path)

    @staticmethod
    def load(path: Path) -> "HDBValuationArtifact":
        artifact = joblib.load(path)
        if not isinstance(artifact, HDBValuationArtifact):
            raise TypeError(f"Artifact at {path} is not a HDBValuationArtifact")
        return artifact


def fit_cqr_calibration(
    y_val: np.ndarray,
    low_val_pred: np.ndarray,
    high_val_pred: np.ndarray,
    nominal_coverage: float = 0.80,
) -> CalibrationResult:
    """Conformalized quantile regression (CQR): the margin is the ``nominal_coverage``-quantile
    of each validation point's worst-case miss (how far below the lower quantile prediction, or
    above the upper one, the true price actually landed), clipped at 0 so a well-calibrated
    quantile model is never needlessly widened."""
    conformity_scores = np.maximum(low_val_pred - y_val, y_val - high_val_pred)
    margin = float(np.quantile(conformity_scores, nominal_coverage))
    margin = max(margin, 0.0)
    return CalibrationResult(conformal_margin=margin, nominal_coverage=nominal_coverage)


def fit_calibration(residuals: pd.Series, nominal_coverage: float = 0.80) -> CalibrationResult:
    """Legacy flat residual-shift calibration, kept only as the fallback path when quantile
    pipelines aren't available (e.g. loading an artifact saved before the CQR rewrite)."""
    alpha = (1 - nominal_coverage) / 2
    lower = float(np.quantile(residuals, alpha))
    upper = float(np.quantile(residuals, 1 - alpha))
    return CalibrationResult(
        conformal_margin=0.0,
        nominal_coverage=nominal_coverage,
        lower_residual_quantile=lower,
        upper_residual_quantile=upper,
    )


__all__ = [
    "TARGET_COLUMN",
    "CalibrationResult",
    "HDBValuationArtifact",
    "fit_calibration",
    "fit_cqr_calibration",
]
