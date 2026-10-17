"""Fetches the real HDB resale transaction dataset from data.gov.sg (public, no API key) and
saves it as a CSV shaped exactly like the historical data.gov.sg extract that
``app.ml.train``/``app.ml.features.prepare_training_frame`` already expect.

Dataset: "Resale flat prices based on registration date from Jan-2017 onwards"
(resource_id d_8b84c4ee58e3cfc0ece0d773c8ca6abc), ~240k+ real transactions, updated monthly.

Usage (from backend/):
    python scripts/fetch_hdb_resale_data.py
    python scripts/fetch_hdb_resale_data.py --limit 50000   # cap row count for a faster run
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

import httpx

RESOURCE_ID = "d_8b84c4ee58e3cfc0ece0d773c8ca6abc"
API_URL = "https://data.gov.sg/api/action/datastore_search"
PAGE_SIZE = 10_000
FIELDS = [
    "month", "town", "flat_type", "block", "street_name", "storey_range",
    "floor_area_sqm", "flat_model", "lease_commence_date", "remaining_lease", "resale_price",
]
OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "hdb_resale_live.csv"


def fetch(limit: int | None, out_path: Path) -> int:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    offset = 0
    total_written = 0
    total_available: int | None = None

    with httpx.Client(timeout=60.0) as client, out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()

        while True:
            page_size = PAGE_SIZE if limit is None else min(PAGE_SIZE, limit - total_written)
            if page_size <= 0:
                break

            print(
                f"[fetch_hdb_resale_data] requesting offset={offset} limit={page_size} "
                f"(written so far: {total_written}"
                + (f"/{total_available}" if total_available else "")
                + ")",
                file=sys.stderr,
            )
            start = time.perf_counter()
            resp = client.get(
                API_URL, params={"resource_id": RESOURCE_ID, "limit": page_size, "offset": offset}
            )
            resp.raise_for_status()
            payload = resp.json()
            if not payload.get("success"):
                raise RuntimeError(f"data.gov.sg API returned success=false: {payload}")

            result = payload["result"]
            total_available = result.get("total", total_available)
            records = result.get("records", [])
            elapsed = time.perf_counter() - start
            print(
                f"[fetch_hdb_resale_data] got {len(records)} records in {elapsed:.1f}s",
                file=sys.stderr,
            )
            if not records:
                break

            for rec in records:
                writer.writerow({k: rec.get(k, "") for k in FIELDS})
            total_written += len(records)
            offset += len(records)

            if total_available is not None and offset >= total_available:
                break
            if limit is not None and total_written >= limit:
                break

    print(
        f"[fetch_hdb_resale_data] done: wrote {total_written} real resale transactions to "
        f"{out_path}",
        file=sys.stderr,
    )
    return total_written


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch the real data.gov.sg HDB resale transaction dataset."
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Cap the number of rows fetched (default: fetch the entire dataset, ~240k+ rows).",
    )
    parser.add_argument("--out", type=Path, default=OUT_PATH, help="Output CSV path.")
    args = parser.parse_args()
    fetch(limit=args.limit, out_path=args.out)


if __name__ == "__main__":
    main()
