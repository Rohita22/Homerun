"""Evaluation metrics shared by training and any standalone re-evaluation run (PRD section 14:
"report MAE / median AE / interval coverage versus comparable-sales baseline, plus subgroup
error analysis by town and flat type").
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def evaluate_predictions(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    y_low: np.ndarray | None = None,
    y_high: np.ndarray | None = None,
    group_keys: pd.DataFrame | None = None,
) -> dict:
    errors = np.abs(y_true - y_pred)
    metrics: dict = {
        "mae": float(np.mean(errors)),
        "median_ae": float(np.median(errors)),
        "n": int(len(y_true)),
    }
    if y_low is not None and y_high is not None:
        covered = (y_true >= y_low) & (y_true <= y_high)
        metrics["interval_empirical_coverage"] = float(np.mean(covered))
        metrics["interval_mean_width"] = float(np.mean(y_high - y_low))
    if group_keys is not None:
        frame = group_keys.copy()
        frame["abs_error"] = errors
        by_town = frame.groupby("town")["abs_error"].mean().round(0).to_dict()
        by_flat_type = frame.groupby("flat_type")["abs_error"].mean().round(0).to_dict()
        metrics["mae_by_town"] = {k: float(v) for k, v in by_town.items()}
        metrics["mae_by_flat_type"] = {k: float(v) for k, v in by_flat_type.items()}
    return metrics
