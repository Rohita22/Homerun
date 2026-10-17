"""Deterministic, regex/keyword-based preference extractor.

This is the default ``LLMProvider`` implementation and the fallback every other implementation
degrades to. It guarantees the P0 requirement "gracefully degrade without LLM" — the chat flow,
structured filter form and templated explanations all keep working with zero external API calls.
"""

from __future__ import annotations

import re

from app.domain.interfaces.llm_provider import ExtractionResult

_SG_TOWNS = [
    "TAMPINES", "BEDOK", "PUNGGOL", "WOODLANDS", "JURONG EAST", "JURONG WEST",
    "SENGKANG", "YISHUN", "ANG MO KIO", "BISHAN", "CLEMENTI", "QUEENSTOWN",
    "TOA PAYOH", "SERANGOON", "HOUGANG", "PASIR RIS", "CHOA CHU KANG",
    "BUKIT BATOK", "BUKIT MERAH", "BUKIT PANJANG", "GEYLANG", "KALLANG",
    "MARINE PARADE", "NOVENA", "SEMBAWANG",
]

_PRICE_PATTERN = re.compile(
    r"(?:under|below|less than|up to|max(?:imum)?(?: of)?)\s*"
    r"(?:s\$|sgd|\$)?\s*([\d,.]+)\s*(k|m|mil|million)?",
    re.IGNORECASE,
)
_BEDROOM_PATTERN = re.compile(r"(\d+)[\s-]*(?:room|bed(?:room)?s?|-room)", re.IGNORECASE)
_PROPERTY_TYPE_PATTERNS = {
    "HDB": re.compile(r"\bhdb\b", re.IGNORECASE),
    "CONDO": re.compile(r"\bcondo(?:minium)?\b", re.IGNORECASE),
    "LANDED": re.compile(r"\blanded\b|\bterrace\b|\bbungalow\b", re.IGNORECASE),
    "EC": re.compile(r"\bexecutive condo(?:minium)?\b|\bec\b", re.IGNORECASE),
}
_RENT_PATTERN = re.compile(r"\brent(?:al)?\b", re.IGNORECASE)


def _parse_price(message: str) -> float | None:
    match = _PRICE_PATTERN.search(message)
    if not match:
        return None
    number_str, unit = match.groups()
    try:
        number = float(number_str.replace(",", ""))
    except ValueError:
        return None
    if unit and unit.lower() in {"m", "mil", "million"}:
        number *= 1_000_000
    elif unit and unit.lower() == "k":
        number *= 1_000
    return number


def _parse_towns(message: str) -> list[str]:
    upper = message.upper()
    return [town for town in _SG_TOWNS if town in upper]


def _parse_soft_weights(message: str) -> dict[str, float]:
    lowered = message.lower()
    weights: dict[str, float] = {}
    commute_terms = ("commute", "mrt", "near the mrt", "transport", "station")
    space_terms = ("space", "bigger", "larger", "floor area")
    if any(term in lowered for term in commute_terms):
        weights["commute_convenience"] = 0.7
    if any(term in lowered for term in space_terms):
        weights["floor_area"] = 0.6
    if "value commute more than space" in lowered or (
        "commute" in lowered and "more than" in lowered and "space" in lowered
    ):
        weights["commute_convenience"] = 0.8
        weights["floor_area"] = 0.3
    if "lease" in lowered or "remaining lease" in lowered:
        weights["lease_remaining"] = 0.5
    return weights


class TemplateLLMProvider:
    """Offline, deterministic buyer-intent extraction. No network calls."""

    name = "template"

    def extract_preferences(self, message: str, existing_profile: dict) -> ExtractionResult:
        patch: dict = {}
        warnings: list[str] = []

        if _RENT_PATTERN.search(message):
            patch["transaction_type"] = "rent"

        for prop_type, pattern in _PROPERTY_TYPE_PATTERNS.items():
            if pattern.search(message):
                patch["property_type"] = prop_type
                break

        price = _parse_price(message)
        if price is not None:
            patch["max_price_sgd"] = price
            patch.setdefault("hard_constraints", []).append("max_price_sgd")

        bedroom_match = _BEDROOM_PATTERN.search(message)
        if bedroom_match:
            patch["min_bedrooms"] = int(bedroom_match.group(1))
            patch.setdefault("hard_constraints", []).append("min_bedrooms")

        towns = _parse_towns(message)
        if towns:
            patch["preferred_towns"] = towns

        soft_weights = _parse_soft_weights(message)
        if soft_weights:
            patch["soft_weights"] = soft_weights

        if "property_type" not in patch and not existing_profile.get("property_type"):
            warnings.append("Could not determine property type; please confirm HDB or Condo.")

        followup = None
        if "max_price_sgd" not in patch and not existing_profile.get("max_price_sgd"):
            followup = "What's your maximum budget in SGD?"
        elif "property_type" not in patch and not existing_profile.get("property_type"):
            followup = "Are you looking for an HDB, Condo, Executive Condo, or Landed property?"

        return ExtractionResult(
            profile_patch=patch, followup_question=followup, warnings=warnings, used_llm=False
        )

    def health(self) -> bool:
        return True
