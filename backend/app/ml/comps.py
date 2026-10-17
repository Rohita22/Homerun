"""How many recent HDB resales back a valuation (the "N past <town> resales" caption).

Counted from the same data.gov.sg resale file the valuation model trains on: transactions for the
listing's town and flat type in the trailing 12 months of the file. Returns ``None`` when the file
is not available, so the UI can say "comparables unavailable" instead of inventing a number.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from app.core.config import BACKEND_ROOT
from app.core.logging import get_logger

logger = get_logger(__name__)
RESALE_CSV = BACKEND_ROOT / "data" / "hdb_resale_live.csv"


@lru_cache(maxsize=1)
def _counts(path: str = str(RESALE_CSV)) -> dict[tuple[str, str], int] | None:
    csv = Path(path)
    if not csv.exists():
        logger.warning("comps_unavailable path=%s", csv)
        return None
    import pandas as pd  # heavy; only needed when the first valuation is rendered

    df = pd.read_csv(csv, usecols=["month", "town", "flat_type"])
    latest = pd.Period(df["month"].max(), freq="M")
    recent = df[pd.PeriodIndex(df["month"], freq="M") > latest - 12]
    grouped = recent.groupby(["town", "flat_type"]).size()
    return {(str(t).upper(), str(f).upper()): int(n) for (t, f), n in grouped.items()}


def comparable_resales(town: str | None, flat_type: str | None) -> int | None:
    counts = _counts()
    if counts is None or not town or not flat_type:
        return None
    return counts.get((town.upper(), flat_type.upper()), 0)
