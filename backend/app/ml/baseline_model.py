"""Comparable-sales median baseline (PRD section 7C: "Train median comparable-sales baseline
versus sklearn HistGradientBoostingRegressor"). This is both the evaluation baseline the trained
model must beat, and the always-available fallback when no trained artifact exists yet.
"""

from __future__ import annotations

import pandas as pd


class ComparableSalesMedianModel:
    """Median resale price grouped by (town, flat_type), falling back to town-only and then the
    overall median as grouping keys become sparse — never fabricates a price for an unseen
    combination."""

    version = "baseline-median-v1"

    def __init__(self) -> None:
        self._by_town_flat_type: dict[tuple[str, str], float] = {}
        self._by_town: dict[str, float] = {}
        self._overall: float | None = None
        self._fitted = False

    def fit(self, df: pd.DataFrame) -> "ComparableSalesMedianModel":
        self._by_town_flat_type = (
            df.groupby(["town", "flat_type"])["resale_price"].median().to_dict()
        )
        self._by_town = df.groupby("town")["resale_price"].median().to_dict()
        self._overall = float(df["resale_price"].median())
        self._fitted = True
        return self

    def predict_one(self, town: str, flat_type: str) -> float | None:
        if not self._fitted:
            return None
        key = (town.upper(), flat_type.upper())
        if key in self._by_town_flat_type:
            return float(self._by_town_flat_type[key])
        if town.upper() in self._by_town:
            return float(self._by_town[town.upper()])
        return self._overall

    def predict(self, df: pd.DataFrame) -> list[float | None]:
        return [self.predict_one(row.town, row.flat_type) for row in df.itertuples()]
