"""Geography helpers: commute estimate to the CBD and a schematic map projection.

Commute is an *estimate*, not a routed journey: straight-line distance to Raffles Place converted
to door-to-door transit minutes (``BASE + PER_KM * km``, fitted so Bishan ≈ 24 min and Jurong West
≈ 48 min). It uses the listing's geocode when there is one, else its town centre, and says which
(``basis``) so callers can label it. No coordinates and no known town -> ``None`` (unknown).
"""

from __future__ import annotations

import math

WORKPLACE_NAME = "Raffles Place"
WORKPLACE = (1.2840, 103.8514)
_BASE_MIN = 7.0
_PER_KM_MIN = 2.2

# Approximate town centres (lat, lon) — only the fallback when a listing has no geocode.
TOWN_CENTRES: dict[str, tuple[float, float]] = {
    "ANG MO KIO": (1.3691, 103.8454), "BEDOK": (1.3236, 103.9273), "BISHAN": (1.3526, 103.8352),
    "BUKIT BATOK": (1.3590, 103.7637), "BUKIT MERAH": (1.2819, 103.8239),
    "BUKIT PANJANG": (1.3774, 103.7719), "BUKIT TIMAH": (1.3294, 103.8021),
    "CENTRAL AREA": (1.2894, 103.8500), "CHOA CHU KANG": (1.3840, 103.7470),
    "CLEMENTI": (1.3162, 103.7649), "GEYLANG": (1.3201, 103.8918), "HOUGANG": (1.3612, 103.8863),
    "JURONG EAST": (1.3329, 103.7436), "JURONG WEST": (1.3404, 103.7090),
    "KALLANG/WHAMPOA": (1.3100, 103.8651), "MARINE PARADE": (1.3020, 103.9072),
    "PASIR RIS": (1.3721, 103.9474), "PUNGGOL": (1.4043, 103.9021), "QUEENSTOWN": (1.2942, 103.7861),
    "SEMBAWANG": (1.4491, 103.8185), "SENGKANG": (1.3868, 103.8914), "SERANGOON": (1.3554, 103.8679),
    "TAMPINES": (1.3496, 103.9568), "TOA PAYOH": (1.3343, 103.8563), "WOODLANDS": (1.4382, 103.7890),
    "YISHUN": (1.4304, 103.8354),
}

# Schematic map: the template draws the island as a blob inside this box (percent of the panel).
_MAP_BOX = {"left": 8.0, "top": 20.0, "width": 84.0, "height": 58.0}
_LAT = (1.205, 1.480)
_LON = (103.620, 104.040)


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(h))


ALL_TOWNS: list[str] = sorted(t.title() for t in TOWN_CENTRES)


def nearby_towns(limit: int = 6) -> dict[str, list[str]]:
    """For each town, the closest other towns (by centre-to-centre distance), nearest first."""
    out: dict[str, list[str]] = {}
    for name, centre in TOWN_CENTRES.items():
        others = sorted((haversine_km(centre, c), n) for n, c in TOWN_CENTRES.items() if n != name)
        out[name.title()] = [n.title() for _, n in others[:limit]]
    return out


def commute_estimate(
    lat: float | None, lon: float | None, town: str | None
) -> tuple[int | None, str | None]:
    """Return ``(minutes, basis)`` where basis is ``"coordinates"``, ``"town_centre"`` or ``None``."""
    if lat is not None and lon is not None:
        point, basis = (lat, lon), "coordinates"
    elif town and town.upper() in TOWN_CENTRES:
        point, basis = TOWN_CENTRES[town.upper()], "town_centre"
    else:
        return None, None
    minutes = _BASE_MIN + _PER_KM_MIN * haversine_km(point, WORKPLACE)
    return int(round(max(8.0, min(80.0, minutes)))), basis


def map_position(lat: float | None, lon: float | None) -> dict[str, float] | None:
    """Percent position inside the schematic map, or ``None`` when the listing has no geocode."""
    if lat is None or lon is None:
        return None
    fx = (lon - _LON[0]) / (_LON[1] - _LON[0])
    fy = 1 - (lat - _LAT[0]) / (_LAT[1] - _LAT[0])
    fx, fy = max(0.0, min(1.0, fx)), max(0.0, min(1.0, fy))
    return {
        "x": round(_MAP_BOX["left"] + fx * _MAP_BOX["width"], 1),
        "y": round(_MAP_BOX["top"] + fy * _MAP_BOX["height"], 1),
    }
