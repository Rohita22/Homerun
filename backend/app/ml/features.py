"""Feature extraction for HDB resale valuation (PRD section 7C): town, flat type, floor area,
storey range, flat model, remaining lease, transaction month. Shared by training, evaluation and
online inference so features can never drift between the two.
"""

from __future__ import annotations

import pandas as pd

from app.domain.entities import PropertyListing

FEATURE_COLUMNS = [
    "town",
    "flat_type",
    "floor_area_sqm",
    "storey_range",
    "flat_model",
    "remaining_lease_years",
    "transaction_month",
]
CATEGORICAL_COLUMNS = ["town", "flat_type", "storey_range", "flat_model"]
NUMERIC_COLUMNS = ["floor_area_sqm", "remaining_lease_years", "transaction_month_ordinal"]
TARGET_COLUMN = "resale_price"


def month_to_ordinal(month_str: str | None) -> int | None:
    """Convert 'YYYY-MM' to a monotonically increasing integer for chronological splitting and
    as a drift-aware numeric feature."""
    if not month_str:
        return None
    try:
        year, month = month_str.split("-")
        return int(year) * 12 + int(month)
    except (ValueError, AttributeError):
        return None


def listing_to_feature_row(listing: PropertyListing) -> dict:
    transaction_month = listing.attributes.get("transaction_month")
    return {
        "town": (listing.town or "UNKNOWN").upper(),
        "flat_type": (listing.flat_type or "UNKNOWN").upper(),
        "floor_area_sqm": listing.floor_area_sqm,
        "storey_range": (listing.storey_range or "UNKNOWN").upper(),
        "flat_model": (listing.flat_model or "UNKNOWN").upper(),
        "remaining_lease_years": listing.lease_remaining_years,
        "transaction_month": transaction_month,
        "transaction_month_ordinal": month_to_ordinal(transaction_month),
    }


def prepare_training_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize a data.gov.sg-shaped HDB resale dataframe into the shared feature schema.

    Expected raw columns (as published by data.gov.sg): month, town, flat_type, storey_range,
    floor_area_sqm, flat_model, remaining_lease, resale_price. ``remaining_lease`` may be either
    a plain year count or a "XX years YY months" string.
    """
    out = pd.DataFrame()
    out["town"] = df["town"].astype(str).str.upper()
    out["flat_type"] = df["flat_type"].astype(str).str.upper()
    out["storey_range"] = df["storey_range"].astype(str).str.upper()
    out["flat_model"] = df["flat_model"].astype(str).str.upper()
    out["floor_area_sqm"] = pd.to_numeric(df["floor_area_sqm"], errors="coerce")
    out["remaining_lease_years"] = df["remaining_lease"].apply(_parse_remaining_lease)
    out["transaction_month"] = df["month"].astype(str)
    out["transaction_month_ordinal"] = out["transaction_month"].apply(month_to_ordinal)
    out[TARGET_COLUMN] = pd.to_numeric(df["resale_price"], errors="coerce")
    return out.dropna(subset=["floor_area_sqm", "transaction_month_ordinal", TARGET_COLUMN])


def _parse_remaining_lease(value) -> float | None:  # noqa: ANN001
    if pd.isna(value):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value)
    years = 0.0
    if "year" in text:
        years += float(text.split("year")[0].strip().split()[-1])
    if "month" in text:
        months_part = text.split("year")[-1] if "year" in text else text
        try:
            months = float(months_part.split("month")[0].strip().split()[-1])
            years += months / 12
        except (ValueError, IndexError):
            pass
    if years == 0.0:
        try:
            years = float(text)
        except ValueError:
            return None
    return years
