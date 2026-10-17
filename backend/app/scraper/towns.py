"""Resolve an HDB town for a scraped listing.

PropertyGuru groups listings under informal areas ("Hougang / Punggol / Sengkang") that map to
several HDB towns, so the label alone is ambiguous. The street, however, identifies the town
exactly: the HDB resale dataset the valuation model is trained on already lists
(block, street_name) -> town for every flat. We use it as a lookup, falling back to the area label
only when it names exactly one town. Anything still ambiguous stays ``None`` so the hard filters
treat it as "needs confirmation" instead of guessing.
"""

from __future__ import annotations

import csv
import re
from functools import lru_cache
from pathlib import Path

from app.core.config import BACKEND_ROOT
from app.core.logging import get_logger

logger = get_logger(__name__)

HDB_TOWNS = [
    "ANG MO KIO", "BEDOK", "BISHAN", "BUKIT BATOK", "BUKIT MERAH", "BUKIT PANJANG",
    "BUKIT TIMAH", "CENTRAL AREA", "CHOA CHU KANG", "CLEMENTI", "GEYLANG", "HOUGANG",
    "JURONG EAST", "JURONG WEST", "KALLANG/WHAMPOA", "MARINE PARADE", "PASIR RIS",
    "PUNGGOL", "QUEENSTOWN", "SEMBAWANG", "SENGKANG", "SERANGOON", "TAMPINES", "TOA PAYOH",
    "WOODLANDS", "YISHUN",
]
# Area-label words that name a town without being its exact HDB spelling.
_LABEL_ALIASES = {
    "KALLANG": "KALLANG/WHAMPOA",
    "WHAMPOA": "KALLANG/WHAMPOA",
    "BOON LAY": "JURONG WEST",
    "LAKESIDE": "JURONG EAST",
    "CHINESE GARDEN": "JURONG EAST",
    "JURONG EAST": "JURONG EAST",
    "JURONG WEST": "JURONG WEST",
}

# HDB's street-name abbreviations (resale CSV) vs the spelled-out names PropertyGuru shows.
_ABBREVIATIONS = {
    "AVENUE": "AVE", "STREET": "ST", "ROAD": "RD", "DRIVE": "DR", "CENTRAL": "CTRL",
    "NORTH": "NTH", "SOUTH": "STH", "BUKIT": "BT", "CRESCENT": "CRES", "LORONG": "LOR",
    "JALAN": "JLN", "CLOSE": "CL", "PLACE": "PL", "GARDENS": "GDNS", "HEIGHTS": "HTS",
    "TERRACE": "TER", "PARK": "PK", "TANJONG": "TG", "UPPER": "UPP", "KAMPONG": "KG",
    "MARKET": "MKT", "LANE": "LN", "BOULEVARD": "BLVD", "COMMONWEALTH": "C'WEALTH",
}
_BLOCK_RE = re.compile(r"^(\d+[A-Za-z]?)\s+(.+)$")


def normalize_street(street: str) -> str:
    words = re.sub(r"[^A-Z0-9' ]", " ", street.upper()).split()
    return " ".join(_ABBREVIATIONS.get(w, w) for w in words)


def split_block_and_street(title: str | None) -> tuple[str | None, str | None]:
    if not title:
        return None, None
    match = _BLOCK_RE.match(title.strip())
    if not match:
        return None, title.strip()
    return match.group(1).upper(), match.group(2)


def towns_in_label(label: str | None) -> set[str]:
    haystack = (label or "").upper()
    found = {t for t in HDB_TOWNS if t in haystack}
    found |= {town for alias, town in _LABEL_ALIASES.items() if alias in haystack}
    return found


class TownResolver:
    def __init__(self, resale_csv: Path | None = None) -> None:
        self._by_block_street: dict[tuple[str, str], str] = {}
        self._by_street: dict[str, set[str]] = {}
        if resale_csv and resale_csv.exists():
            self._load(resale_csv)
        else:
            logger.warning("town_resolver_no_resale_csv path=%s (falling back to area labels)", resale_csv)

    def _load(self, path: Path) -> None:
        with path.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                street = normalize_street(row["street_name"])
                town = row["town"].upper()
                self._by_block_street[(row["block"].upper(), street)] = town
                self._by_street.setdefault(street, set()).add(town)
        logger.info("town_resolver_loaded blocks=%d streets=%d", len(self._by_block_street), len(self._by_street))

    def resolve(self, title: str | None, area_label: str | None) -> str | None:
        block, street = split_block_and_street(title)
        if street:
            street_key = normalize_street(street)
            if block and (block, street_key) in self._by_block_street:
                return self._by_block_street[(block, street_key)]
            street_towns = self._by_street.get(street_key, set())
            if len(street_towns) == 1:
                return next(iter(street_towns))
        label_towns = towns_in_label(area_label)
        if len(label_towns) == 1:
            return next(iter(label_towns))
        return None


@lru_cache
def get_town_resolver() -> TownResolver:
    return TownResolver(BACKEND_ROOT / "data" / "hdb_resale_live.csv")
