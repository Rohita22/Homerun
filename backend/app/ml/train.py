"""Training entry point for the HDB resale valuation model (PRD section 7C/15).

Usage (from backend/):
    python -m app.ml.train --data-path path/to/hdb-resale-flat-prices.csv
    python -m app.ml.train                      # bootstraps a small synthetic dataset instead

Chronological train/validation/test splits (by transaction month) prevent future leakage, per
PRD section 7C. A synthetic dataset is used only when no real data.gov.sg extract is supplied,
so the repository is runnable end-to-end offline; it is clearly labeled as synthetic in the
saved metadata and must never be presented as real market evidence.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.inspection import permutation_importance
from sklearn.model_selection import RandomizedSearchCV

from app.core.config import get_settings
from app.core.logging import get_logger
from app.ml.baseline_model import ComparableSalesMedianModel
from app.ml.evaluate import evaluate_predictions
from app.ml.features import CATEGORICAL_COLUMNS, NUMERIC_COLUMNS, TARGET_COLUMN, prepare_training_frame
from app.ml.hgb_model import HDBValuationArtifact, fit_cqr_calibration

SEED = 42
MODEL_FILENAME = "hdb_valuation_model.joblib"
METRICS_FILENAME = "hdb_valuation_metrics.json"
NOMINAL_COVERAGE = 0.80

logger = get_logger(__name__)


def _synthetic_dataset(n: int = 4000, seed: int = SEED) -> pd.DataFrame:
    """Deterministic synthetic HDB resale dataset for offline bootstrapping/CI, shaped exactly
    like the data.gov.sg extract so :func:`prepare_training_frame` handles both identically."""
    rng = np.random.default_rng(seed)
    towns = [
        "TAMPINES", "BEDOK", "PUNGGOL", "WOODLANDS", "JURONG WEST", "SENGKANG",
        "YISHUN", "ANG MO KIO", "BISHAN", "CLEMENTI",
    ]
    flat_types = ["2 ROOM", "3 ROOM", "4 ROOM", "5 ROOM", "EXECUTIVE"]
    flat_type_base_area = {"2 ROOM": 45, "3 ROOM": 68, "4 ROOM": 92, "5 ROOM": 112, "EXECUTIVE": 130}
    flat_models = ["Model A", "Improved", "New Generation", "Premium Apartment", "Simplified"]
    town_base_price_psm = {
        "TAMPINES": 5600, "BEDOK": 5400, "PUNGGOL": 5300, "WOODLANDS": 4600,
        "JURONG WEST": 4700, "SENGKANG": 5100, "YISHUN": 4500, "ANG MO KIO": 5800,
        "BISHAN": 6400, "CLEMENTI": 6100,
    }
    months = [f"{y}-{m:02d}" for y in (2023, 2024, 2025, 2026) for m in range(1, 13)]
    months = months[: months.index("2026-09") + 1]

    rows = []
    for _ in range(n):
        town = rng.choice(towns)
        flat_type = rng.choice(flat_types)
        base_area = flat_type_base_area[flat_type]
        floor_area = max(35, rng.normal(base_area, 6))
        storey = rng.choice(["01 TO 03", "04 TO 06", "07 TO 09", "10 TO 12", "13 TO 15", "16 TO 18"])
        storey_mid = {"01 TO 03": 2, "04 TO 06": 5, "07 TO 09": 8, "10 TO 12": 11,
                       "13 TO 15": 14, "16 TO 18": 17}[storey]
        flat_model = rng.choice(flat_models)
        remaining_lease = max(40, rng.normal(70, 12))
        month = rng.choice(months)
        month_idx = months.index(month)
        drift = 1 + 0.004 * month_idx  # mild upward price drift over time
        psm = town_base_price_psm[town] * drift
        price = (
            psm * floor_area
            + storey_mid * 1800
            + (remaining_lease - 70) * 900
            + rng.normal(0, 18000)
        )
        rows.append(
            {
                "month": month,
                "town": town,
                "flat_type": flat_type,
                "storey_range": storey,
                "floor_area_sqm": round(floor_area, 1),
                "flat_model": flat_model,
                "remaining_lease": round(remaining_lease, 1),
                "resale_price": round(max(price, 150_000), -2),
            }
        )
    return pd.DataFrame(rows)


def _chronological_split(
    df: pd.DataFrame, train_frac: float = 0.7, val_frac: float = 0.15
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    df = df.sort_values("transaction_month_ordinal").reset_index(drop=True)
    n = len(df)
    train_end = int(n * train_frac)
    val_end = int(n * (train_frac + val_frac))
    return df.iloc[:train_end], df.iloc[train_end:val_end], df.iloc[val_end:]


def _tune_point_hyperparameters(
    train_df: pd.DataFrame, feature_cols: list[str], n_iter: int = 6, cv: int = 3
) -> dict:
    """Bounded random search over a small, sane grid. Kept deliberately small (n_iter * cv fits)
    so a hackathon training run stays on the order of minutes even on the real ~240k-row
    dataset, not an unbounded search."""
    param_distributions = {
        "model__max_depth": [4, 6, 8, 10, None],
        "model__learning_rate": [0.03, 0.05, 0.08, 0.12],
        "model__max_iter": [200, 300, 400],
        "model__l2_regularization": [0.0, 0.1, 0.5, 1.0],
        "model__min_samples_leaf": [10, 20, 40],
    }
    base_pipeline = HDBValuationArtifact.build_pipeline(random_state=SEED)
    search = RandomizedSearchCV(
        base_pipeline,
        param_distributions=param_distributions,
        n_iter=n_iter,
        cv=cv,
        scoring="neg_mean_absolute_error",
        random_state=SEED,
        n_jobs=-1,
    )
    start = time.perf_counter()
    search.fit(train_df[feature_cols], train_df[TARGET_COLUMN])
    elapsed = time.perf_counter() - start
    logger.info(
        "hyperparameter_search_complete best_mae=%.0f elapsed_s=%.1f best_params=%s",
        -search.best_score_, elapsed, search.best_params_,
    )
    return {k.removeprefix("model__"): v for k, v in search.best_params_.items()}


def train(
    data_path: str | None = None,
    out_dir: Path | None = None,
    synthetic_n: int = 4000,
    tune: bool = False,
) -> dict:
    out_dir = out_dir or get_settings().ml_artifacts_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    is_synthetic = data_path is None
    logger.info("training_data_load_start data_path=%s synthetic=%s", data_path, is_synthetic)
    raw = pd.read_csv(data_path) if data_path else _synthetic_dataset(n=synthetic_n)
    df = prepare_training_frame(raw)
    logger.info("training_data_prepared n_rows=%d", len(df))

    train_df, val_df, test_df = _chronological_split(df)
    feature_cols = CATEGORICAL_COLUMNS + NUMERIC_COLUMNS

    best_hyperparams: dict | None = None
    point_kwargs: dict = {}
    if tune:
        best_hyperparams = _tune_point_hyperparameters(train_df, feature_cols)
        point_kwargs = dict(best_hyperparams)

    logger.info("fitting_point_model hyperparams=%s", point_kwargs or "default")
    pipeline_point = HDBValuationArtifact.build_pipeline(
        random_state=SEED, loss="squared_error", **point_kwargs
    )
    pipeline_point.fit(train_df[feature_cols], train_df[TARGET_COLUMN])

    alpha = (1 - NOMINAL_COVERAGE) / 2
    logger.info("fitting_quantile_models lower_q=%.3f upper_q=%.3f", alpha, 1 - alpha)
    pipeline_low = HDBValuationArtifact.build_pipeline(
        random_state=SEED, loss="quantile", quantile=alpha, **point_kwargs
    )
    pipeline_low.fit(train_df[feature_cols], train_df[TARGET_COLUMN])
    pipeline_high = HDBValuationArtifact.build_pipeline(
        random_state=SEED, loss="quantile", quantile=1 - alpha, **point_kwargs
    )
    pipeline_high.fit(train_df[feature_cols], train_df[TARGET_COLUMN])

    val_low_pred = pipeline_low.predict(val_df[feature_cols])
    val_high_pred = pipeline_high.predict(val_df[feature_cols])
    calibration = fit_cqr_calibration(
        val_df[TARGET_COLUMN].to_numpy(), val_low_pred, val_high_pred, NOMINAL_COVERAGE
    )
    calibration.fitted_on_months = sorted(val_df["transaction_month_ordinal"].unique().tolist())
    logger.info("cqr_calibration_fitted conformal_margin=%.0f", calibration.conformal_margin)

    feature_importance_result = permutation_importance(
        pipeline_point, test_df[feature_cols], test_df[TARGET_COLUMN],
        n_repeats=5, random_state=SEED, scoring="neg_mean_absolute_error",
    )
    feature_importances = {
        col: round(float(imp), 4)
        for col, imp in sorted(
            zip(feature_cols, feature_importance_result.importances_mean),
            key=lambda pair: pair[1], reverse=True,
        )
    }
    logger.info("feature_importances=%s", feature_importances)

    model_version = f"hgb-cqr-{datetime.now(tz=timezone.utc).strftime('%Y%m%d%H%M%S')}"
    artifact = HDBValuationArtifact(
        pipeline_point, calibration, version=model_version,
        pipeline_low=pipeline_low, pipeline_high=pipeline_high,
        feature_importances=feature_importances,
    )

    test_pred, test_low, test_high = artifact.predict_with_interval(test_df)
    hgb_metrics = evaluate_predictions(
        y_true=test_df[TARGET_COLUMN].to_numpy(),
        y_pred=test_pred,
        y_low=test_low,
        y_high=test_high,
        group_keys=test_df[["town", "flat_type"]],
    )

    baseline = ComparableSalesMedianModel().fit(train_df)
    baseline_pred = np.array(baseline.predict(test_df))
    baseline_pred = np.where(baseline_pred == None, np.nanmedian(train_df[TARGET_COLUMN]), baseline_pred).astype(float)  # noqa: E711
    baseline_metrics = evaluate_predictions(
        y_true=test_df[TARGET_COLUMN].to_numpy(), y_pred=baseline_pred
    )

    artifact.save(out_dir / MODEL_FILENAME)
    logger.info("artifact_saved path=%s version=%s", out_dir / MODEL_FILENAME, model_version)

    metrics = {
        "model_version": model_version,
        "trained_at": datetime.now(tz=timezone.utc).isoformat(),
        "is_synthetic_training_data": is_synthetic,
        "data_source": data_path or "synthetic_bootstrap_v1",
        "seed": SEED,
        "n_train": len(train_df),
        "n_val": len(val_df),
        "n_test": len(test_df),
        "hyperparameter_search": {"ran": tune, "best_params": best_hyperparams},
        "feature_importances_mae_increase": feature_importances,
        "calibration": asdict(calibration),
        "hgb_test_metrics": hgb_metrics,
        "baseline_median_test_metrics": baseline_metrics,
        "beats_baseline": hgb_metrics["mae"] < baseline_metrics["mae"],
    }
    (out_dir / METRICS_FILENAME).write_text(json.dumps(metrics, indent=2))
    logger.info("training_complete mae=%.0f beats_baseline=%s", hgb_metrics["mae"], metrics["beats_baseline"])
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the Homerun HDB valuation model.")
    parser.add_argument(
        "--data-path",
        default=None,
        help="Path to a data.gov.sg HDB resale CSV. Omit to bootstrap from synthetic data.",
    )
    parser.add_argument(
        "--tune",
        action="store_true",
        help="Run a bounded RandomizedSearchCV over HGB hyperparameters before the final fit.",
    )
    args = parser.parse_args()
    metrics = train(data_path=args.data_path, tune=args.tune)
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
