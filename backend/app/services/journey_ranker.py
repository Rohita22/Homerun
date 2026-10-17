"""The Homerun UI's four-slider ranking: commute, MRT, space, price.

``MultiObjectiveRanker`` (the PRD's general ranker) scores abstract features; the product design
exposes exactly four preferences the buyer can weight 0-10, so this ranker scores those and
returns the per-factor breakdown the "why this rank?" panel renders. Rules it keeps from the
design: an unknown value never scores best-case (it takes a neutral 0.5 and a 6-point penalty),
and weights are renormalised so the sliders only express *relative* importance.
"""

from __future__ import annotations

from app.domain.entities import BuyerProfile, PropertyListing, RankedItem
from app.journey.geo import commute_estimate
from app.journey.views import parse_mrt

FACTOR_LABELS = {"commute": "commute", "mrt": "MRT", "area": "space", "price": "under budget"}
DEFAULT_WEIGHTS = {"commute": 8.0, "mrt": 5.0, "area": 3.0, "price": 3.0}
UNKNOWN_PENALTY = 0.06


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def normalise_weights(raw: dict[str, float] | None) -> dict[str, float]:
    merged = dict(DEFAULT_WEIGHTS)
    for key in DEFAULT_WEIGHTS:
        if raw and raw.get(key) is not None:
            merged[key] = max(0.0, min(10.0, float(raw[key])))
    return merged


def factor_scores(listing: PropertyListing, budget: float) -> dict[str, float | None]:
    mrt_min, _ = parse_mrt((listing.attributes or {}).get("mrt"))
    commute, _ = commute_estimate(listing.latitude, listing.longitude, listing.town)
    price = listing.asking_price_sgd
    return {
        "commute": None if commute is None else _clamp((50 - commute) / 35),
        "mrt": None if mrt_min is None else _clamp((15 - mrt_min) / 12),
        "area": None if listing.floor_area_sqm is None else _clamp((listing.floor_area_sqm - 75) / 25),
        "price": None if price is None or not budget else _clamp((budget - price) / (budget * 0.35)),
    }


class JourneyRanker:
    version = "journey-ranker-v1"

    def rank(
        self,
        listings: list[PropertyListing],
        profile: BuyerProfile,
        weights: dict[str, float] | None = None,
        limit: int = 5,
    ) -> list[RankedItem]:
        w = normalise_weights(weights or profile.soft_weights)
        total = sum(w.values()) or 1.0
        budget = profile.max_price_sgd or 0.0
        scored: list[RankedItem] = []
        for listing in listings:
            scores = factor_scores(listing, budget)
            raw = penalty = 0.0
            factors: dict[str, float] = {}
            detail_factors = []
            for key in DEFAULT_WEIGHTS:
                s = scores[key]
                if s is None:
                    penalty += UNKNOWN_PENALTY
                contribution = (0.5 if s is None else s) * w[key] / total
                raw += contribution
                factors[key] = round(contribution, 4)
                detail_factors.append(
                    {"k": key, "label": FACTOR_LABELS[key], "s": s, "c": round(contribution, 4),
                     "max": round(w[key] / total, 4)}
                )
            score = max(0, round((raw - penalty) * 100))
            scored.append(
                RankedItem(
                    listing_id=listing.listing_id, rank=0, score=float(score), factors=factors,
                    reasons=[],
                    detail={"factors": detail_factors, "penalty": round(penalty, 4)},
                )
            )
        scored.sort(key=lambda item: (-item.score, item.listing_id))
        top = scored[:limit]
        for idx, item in enumerate(top, start=1):
            item.rank = idx
        return top
