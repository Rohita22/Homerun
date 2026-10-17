"""Chat message -> the UI's profile fields.

The LLM (Gemini, or the offline template extractor) returns a loose profile patch. This module
turns that patch plus the raw wording into what the profile screen shows: the four slider
weights, the town chips and the "what I heard" lists. The wording rules (e.g. "commute matters
more than size" -> commute up, space down) are deterministic so they work with no LLM at all.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.schemas.journey import UIProfile

_COMMUTE = re.compile(r"commut|raffles|\bcbd\b|\boffice\b|\bwork\b|travel time", re.I)
_MRT = re.compile(r"\bmrt\b|\blrt\b|\bstation\b|\btrain\b|public transport", re.I)
_SPACE = re.compile(r"\bspace\b|\bsize\b|\bbigger\b|\blarger\b|\bspacious\b|\broomy\b|floor area|\bsqft\b", re.I)
_SPACE_DOWN = re.compile(
    r"(more than|beats|over|rather than|instead of|not as important as)\s+(the\s+)?(space|size)"
    r"|(space|size)\s+(doesn'?t|does not|isn'?t|is not|matters? less|is less)",
    re.I,
)
_PRICE = re.compile(r"\bcheap|afford|value for money|bargain|\bunder budget|\blow price", re.I)
# LLM output is only trusted for what the buyer actually wrote (a model can "helpfully" fill in a
# property type or budget nobody mentioned, which would silently turn a must-have on).
_SAYS_TYPE = re.compile(r"\bhdb\b|condo|\bec\b|executive|apartment|\bflat\b|landed", re.I)
_SAYS_BEDS = re.compile(r"\d|\b(one|two|three|four|five|studio)\b|bed|room", re.I)
_SAYS_BUDGET = re.compile(r"\d", re.I)
_NO_LIMIT = re.compile(r"no (budget )?(limit|cap)|any budget|budget (is )?(flexible|no issue)|money is no|unlimited", re.I)
_ANYWHERE = re.compile(r"anywhere|any (town|area|where|location)|don'?t mind (the )?(town|area|where|location)|no preference", re.I)
_STRONG = re.compile(r"matters? (more|most|a lot)|most important|priority|beats|must|really", re.I)
_LEGACY_WEIGHT_KEYS = {
    "floor_area": "area",
    "affordability_headroom": "price",
    "commute": "commute", "mrt": "mrt", "area": "area", "price": "price",
}


@dataclass
class Heard:
    must: list[str] = field(default_factory=list)
    nice: list[str] = field(default_factory=list)
    ask: list[str] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)
    got: set[str] = field(default_factory=set)  # must-have topics this message settled: budget|bedrooms|type|town

    def chips(self) -> list[dict]:
        out = []
        for cat, labels in (("must", self.must), ("nice", self.nice), ("ask", self.ask), ("unk", self.unknown)):
            out.extend({"label": label, "cat": cat} for label in labels)
        return out


NO_LIMIT_BUDGET = 5_000_000.0


def k(n: float) -> str:
    return f"${round(n / 1000):,}k"


def weights_from_text(message: str) -> dict[str, float]:
    """Slider values for the topics the buyer explicitly talked about (and only those)."""
    weights: dict[str, float] = {}
    strong = bool(_STRONG.search(message))
    if _COMMUTE.search(message):
        weights["commute"] = 9.0 if strong else 8.0
    if _MRT.search(message):
        weights["mrt"] = 6.0
    if _SPACE.search(message):
        weights["area"] = 2.0 if _SPACE_DOWN.search(message) else 7.0
    if _PRICE.search(message):
        weights["price"] = 6.0
    return weights


def merge_llm_weights(weights: dict[str, float], llm_weights: dict | None) -> dict[str, float]:
    """LLM weights are 0-1 (legacy keys) or 0-10 (UI keys); only fold in keys it actually set."""
    merged = dict(weights)
    for raw_key, value in (llm_weights or {}).items():
        key = _LEGACY_WEIGHT_KEYS.get(raw_key)
        if key is None or not isinstance(value, (int, float)):
            continue
        scaled = value * 10 if value <= 1 else value
        merged[key] = max(0.0, min(10.0, float(scaled)))
    return merged


def apply_patch(
    ui: UIProfile, patch: dict, message: str, ui_towns: list[str]
) -> tuple[UIProfile, Heard, list[str]]:
    """Fold an extraction patch into the UI profile. Returns (profile, heard, warnings)."""
    heard, warnings = Heard(), []
    data = ui.model_copy(deep=True)

    if patch.get("transaction_type") == "rent":
        warnings.append("Homerun searches homes for sale; rentals aren't covered yet.")

    patch = dict(patch)
    if not _SAYS_BUDGET.search(message):
        patch.pop("max_price_sgd", None)
    if not _SAYS_BEDS.search(message):
        patch.pop("min_bedrooms", None)
    if not _SAYS_TYPE.search(message):
        patch.pop("property_type", None)
        patch.pop("property_types", None)
    patch["preferred_towns"] = [
        t for t in patch.get("preferred_towns") or [] if t and t.lower() in message.lower()
    ]

    if patch.get("max_price_sgd"):
        data.budget = float(patch["max_price_sgd"])
        heard.must.append(f"≤ {k(data.budget)}")
        heard.got.add("budget")
    elif _NO_LIMIT.search(message):
        data.budget = NO_LIMIT_BUDGET
        heard.must.append("no budget cap")
        heard.got.add("budget")
    if patch.get("min_bedrooms") is not None:
        data.min_bed = max(0, min(5, int(patch["min_bedrooms"])))
        heard.must.append(f"{data.min_bed}+ bedrooms")
        heard.got.add("bedrooms")

    asked = [t for t in patch.get("preferred_towns") or []]
    if asked:
        by_upper = {t.upper(): t for t in ui_towns}
        found = [by_upper[t.upper()] for t in asked if t.upper() in by_upper]
        missing = [t.title() for t in asked if t.upper() not in by_upper]
        if found:
            data.towns = found
            heard.must.extend(found)
            heard.got.add("town")
        if missing:
            warnings.append(
                f"{', '.join(missing)} isn't in this version's town list ({', '.join(ui_towns)})."
            )

    types = [t for t in [patch.get("property_type"), *(patch.get("property_types") or [])] if t]
    if types:
        labels = sorted({"HDB" if t == "HDB" else "Condo" for t in types if t in {"HDB", "CONDO", "EC"}})
        if labels:
            data.types = labels
            heard.must.append(" + ".join(labels))
            heard.got.add("type")

    if "town" not in heard.got and _ANYWHERE.search(message):
        data.towns = list(ui_towns)
        heard.must.append("any town")
        heard.got.add("town")

    # model weights first, then explicit wording on top: "matters more than size" beats a guess
    data.weights = {
        **merge_llm_weights(data.weights, patch.get("soft_weights")),
        **weights_from_text(message),
    }
    if _COMMUTE.search(message):
        heard.nice.append("short commute → Raffles Pl")
    if _MRT.search(message):
        heard.nice.append("near an MRT")
    if _SPACE.search(message):
        heard.nice.append("space: lower priority" if data.weights["area"] <= 3 else "more space")
    if _PRICE.search(message):
        heard.nice.append("under budget")

    heard.unknown.append("lease length · not said")
    return data, heard, warnings
