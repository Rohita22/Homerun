"""Collects the four buyer-preference answers (budget, bedrooms, property type, town) that the
voice assistant extracts from a free-form conversation.

Pure state + normalisation, no I/O, so it is unit-testable and independent of the Gemini
transport. The answer shape matches what ``QuestionFlow`` submits to ``PUT /api/preferences``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

TOWNS = [
    "ANG MO KIO", "BEDOK", "BISHAN", "BUKIT BATOK", "BUKIT MERAH", "BUKIT PANJANG", "BUKIT TIMAH",
    "CENTRAL AREA", "CHOA CHU KANG", "CLEMENTI", "GEYLANG", "HOUGANG", "JURONG EAST", "JURONG WEST",
    "KALLANG/WHAMPOA", "MARINE PARADE", "PASIR RIS", "PUNGGOL", "QUEENSTOWN", "SEMBAWANG",
    "SENGKANG", "SERANGOON", "TAMPINES", "TOA PAYOH", "WOODLANDS", "YISHUN",
]
PROPERTY_TYPES = ["HDB", "CONDO", "EC", "LANDED"]

_TYPE_ALIASES = {
    "CONDOMINIUM": "CONDO",
    "APARTMENT": "CONDO",
    "EXECUTIVE CONDO": "EC",
    "EXECUTIVE CONDOMINIUM": "EC",
    "HOUSE": "LANDED",
    "TERRACE": "LANDED",
    "SEMI-DETACHED": "LANDED",
    "BUNGALOW": "LANDED",
    "FLAT": "HDB",
}

QUESTION_LABELS = {
    "budget": "maximum budget",
    "bedrooms": "number of bedrooms",
    "property_type": "type of property (HDB, condo, EC or landed)",
    "town": "preferred town or area (or whether anywhere is fine)",
}


def normalise_town(raw: str) -> str:
    town = " ".join(raw.upper().replace("-", " ").split())
    if town in TOWNS:
        return town
    for known in TOWNS:
        if known.split("/")[0] == town:  # "KALLANG" -> "KALLANG/WHAMPOA"
            return known
    return town


def normalise_type(raw: str) -> str | None:
    value = " ".join(raw.upper().split())
    value = _TYPE_ALIASES.get(value, value)
    return value if value in PROPERTY_TYPES else None


@dataclass
class VoicePreferences:
    max_price_sgd: int | None = None
    no_budget_limit: bool = False
    bedrooms: list[int] = field(default_factory=list)
    property_types: list[str] = field(default_factory=list)
    towns: list[str] = field(default_factory=list)
    anywhere: bool = False

    def update(self, args: dict[str, Any]) -> None:
        """Merge a ``save_preferences`` tool call; only supplied fields change (later wins)."""
        budget = args.get("budget_sgd")
        if isinstance(budget, (int, float)) and budget > 0:
            self.max_price_sgd, self.no_budget_limit = int(budget), False
        if args.get("no_budget_limit") is True:
            self.max_price_sgd, self.no_budget_limit = None, True

        beds = [int(b) for b in args.get("bedrooms") or [] if isinstance(b, (int, float)) and b >= 1]
        if beds:
            self.bedrooms = sorted({min(b, 5) for b in beds})

        types = [t for t in (normalise_type(str(x)) for x in args.get("property_types") or []) if t]
        if types:
            self.property_types = list(dict.fromkeys(types))

        towns = [normalise_town(str(t)) for t in args.get("towns") or [] if str(t).strip()]
        if towns:
            self.towns, self.anywhere = list(dict.fromkeys(towns)), False
        if args.get("anywhere_in_singapore") is True:
            self.towns, self.anywhere = [], True

    def answered(self) -> dict[str, bool]:
        return {
            "budget": self.max_price_sgd is not None or self.no_budget_limit,
            "bedrooms": bool(self.bedrooms),
            "property_type": bool(self.property_types),
            "town": bool(self.towns) or self.anywhere,
        }

    def missing(self) -> list[str]:
        return [k for k, done in self.answered().items() if not done]

    @property
    def complete(self) -> bool:
        return not self.missing()

    def snapshot(self) -> dict[str, Any]:
        return {
            "max_price_sgd": self.max_price_sgd,
            "no_budget_limit": self.no_budget_limit,
            "bedrooms": self.bedrooms,
            "property_types": self.property_types,
            "towns": self.towns,
            "anywhere": self.anywhere,
            "answered": self.answered(),
        }

    def to_profile_payload(self) -> dict[str, Any]:
        """Body for ``PUT /api/preferences`` — mirrors ``QuestionFlow.submit``."""
        types = self.property_types
        hard = ["property_type", "min_bedrooms"]
        if self.max_price_sgd is not None:
            hard.append("max_price_sgd")
        if self.towns:
            hard.append("preferred_towns")
        return {
            "transaction_type": "buy",
            "property_type": types[0] if len(types) == 1 else None,
            "property_types": types if len(types) > 1 else [],
            "max_price_sgd": self.max_price_sgd,
            "min_price_sgd": None,
            "min_bedrooms": min(self.bedrooms),
            "min_bathrooms": None,
            "min_floor_area_sqm": None,
            "preferred_towns": self.towns,
            "hard_constraints": hard,
            "soft_weights": {},
            "notes": None,
        }
