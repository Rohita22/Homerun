"""Valuation model contract. Lets ``app.ml`` swap the baseline comparable-sales median for the
trained HistGradientBoostingRegressor (or an s390x-compatible alternative) without the
Valuation agent changing at all.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.domain.entities import PropertyListing, ValuationResult


@runtime_checkable
class ValuationModel(Protocol):
    version: str

    def is_supported(self, listing: PropertyListing) -> bool:
        ...

    def predict(self, listing: PropertyListing) -> ValuationResult:
        ...
