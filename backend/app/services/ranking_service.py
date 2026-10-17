"""Hard constraint filtering and multiobjective ranking (PRD section 7A/7B).

Two single-purpose classes:

``HardFilterService`` separates hard constraints (transaction intent, max price, property type,
min bedrooms, and any buyer-flagged field) from soft preferences, using only verified record
attributes. A listing missing a field needed to evaluate a hard constraint is routed to
``needs_confirmation`` rather than assumed compliant — it is never silently included or excluded.

``MultiObjectiveRanker`` computes a weighted utility over normalized features for the listings
that survive hard filtering, applies a diversity pass so five results are not near-duplicates,
and returns per-feature contributions so the UI can show "why this ranked here" (PRD: "Return
each ranking feature and contribution").
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.entities import BuyerProfile, PropertyListing, RankedItem

# Core fields enforced as hard constraints whenever the buyer specifies a value, independent of
# BuyerProfile.hard_constraints (matches PRD QA cases: "under 700k" excludes 701k without the
# buyer separately flagging price as a deal breaker).
_ALWAYS_HARD_IF_SET = {"transaction_type", "property_type", "max_price_sgd", "min_bedrooms"}


@dataclass
class HardFilterResult:
    eligible: list[PropertyListing] = field(default_factory=list)
    excluded: list[dict] = field(default_factory=list)  # {listing_id, reasons}
    needs_confirmation: list[dict] = field(default_factory=list)  # {listing_id, reasons}


class HardFilterService:
    def apply(self, listings: list[PropertyListing], profile: BuyerProfile) -> HardFilterResult:
        result = HardFilterResult()
        active_hard_fields = _ALWAYS_HARD_IF_SET | set(profile.hard_constraints)

        for listing in listings:
            reasons_exclude: list[str] = []
            reasons_confirm: list[str] = []

            if "transaction_type" in active_hard_fields:
                listing_tx = getattr(listing.transaction_type, "value", listing.transaction_type)
                profile_tx = getattr(profile.transaction_type, "value", profile.transaction_type)
                if listing_tx != profile_tx:
                    reasons_exclude.append(
                        f"transaction_type {listing_tx} does not match requested {profile_tx}"
                    )

            if "property_type" in active_hard_fields and profile.property_type is not None:
                listing_type = getattr(listing.property_type, "value", listing.property_type)
                profile_type = getattr(profile.property_type, "value", profile.property_type)
                if listing_type != profile_type:
                    reasons_exclude.append(
                        f"property_type {listing_type} does not match requested {profile_type}"
                    )

            if "max_price_sgd" in active_hard_fields and profile.max_price_sgd is not None:
                if listing.asking_price_sgd is None:
                    reasons_confirm.append("asking price unknown; cannot verify budget fit")
                elif listing.asking_price_sgd > profile.max_price_sgd:
                    reasons_exclude.append(
                        f"price S${listing.asking_price_sgd:,.0f} exceeds max "
                        f"S${profile.max_price_sgd:,.0f}"
                    )
            if profile.min_price_sgd is not None and listing.asking_price_sgd is not None:
                if listing.asking_price_sgd < profile.min_price_sgd:
                    reasons_exclude.append("price below requested minimum")

            if "min_bedrooms" in active_hard_fields and profile.min_bedrooms is not None:
                if listing.bedrooms is None:
                    reasons_confirm.append("bedroom count unknown; cannot verify room requirement")
                elif listing.bedrooms < profile.min_bedrooms:
                    reasons_exclude.append(
                        f"{listing.bedrooms} bedrooms fewer than required {profile.min_bedrooms}"
                    )

            if "min_floor_area_sqm" in active_hard_fields and profile.min_floor_area_sqm:
                if listing.floor_area_sqm is None:
                    reasons_confirm.append("floor area unknown; cannot verify size requirement")
                elif listing.floor_area_sqm < profile.min_floor_area_sqm:
                    reasons_exclude.append("floor area below requested minimum")

            if "preferred_towns" in active_hard_fields and profile.preferred_towns:
                if listing.town is None:
                    reasons_confirm.append("town unknown; cannot verify location requirement")
                elif listing.town.upper() not in {t.upper() for t in profile.preferred_towns}:
                    reasons_exclude.append(f"town {listing.town} not in preferred towns")

            listing_status = getattr(listing.status, "value", listing.status)
            if listing_status == "inactive":
                reasons_exclude.append("listing is no longer active")

            if reasons_exclude:
                result.excluded.append({"listing_id": listing.listing_id, "reasons": reasons_exclude})
            elif reasons_confirm:
                result.needs_confirmation.append(
                    {"listing_id": listing.listing_id, "reasons": reasons_confirm}
                )
            else:
                result.eligible.append(listing)

        return result


def _normalize(value: float, lo: float, hi: float, invert: bool = False) -> float:
    if hi <= lo:
        return 0.5
    norm = max(0.0, min(1.0, (value - lo) / (hi - lo)))
    return 1 - norm if invert else norm


DEFAULT_WEIGHTS = {
    "affordability_headroom": 0.30,
    "commute_convenience": 0.20,
    "floor_area": 0.20,
    "lease_remaining": 0.15,
    "freshness": 0.15,
}


class MultiObjectiveRanker:
    """Utility = sum(weight_i * normalized_feature_i) - penalties for uncertainty/incomplete
    data, with a lightweight diversity pass (greedy MMR-style re-ordering by town so five results
    are not near-duplicates of each other)."""

    def rank(
        self,
        listings: list[PropertyListing],
        profile: BuyerProfile,
        weights: dict[str, float] | None = None,
        limit: int = 5,
    ) -> list[RankedItem]:
        if not listings:
            return []
        weights = {**DEFAULT_WEIGHTS, **(weights or profile.soft_weights or {})}

        prices = [listing_.asking_price_sgd for listing_ in listings if listing_.asking_price_sgd]
        areas = [listing_.floor_area_sqm for listing_ in listings if listing_.floor_area_sqm]
        leases = [
            listing_.lease_remaining_years
            for listing_ in listings
            if listing_.lease_remaining_years is not None
        ]
        budget = profile.max_price_sgd or (max(prices) if prices else 1.0)

        scored: list[RankedItem] = []
        for listing in listings:
            factors: dict[str, float] = {}
            penalty = 0.0

            if listing.asking_price_sgd is not None and budget:
                headroom = max(0.0, (budget - listing.asking_price_sgd) / budget)
                factors["affordability_headroom"] = round(min(1.0, headroom), 4)
            else:
                penalty += 0.05

            mrt_minutes = (listing.attributes or {}).get("mrt_walk_minutes")
            if mrt_minutes is not None:
                factors["commute_convenience"] = round(_normalize(mrt_minutes, 3, 30, invert=True), 4)
            else:
                penalty += 0.05

            if listing.floor_area_sqm is not None and areas:
                factors["floor_area"] = round(
                    _normalize(listing.floor_area_sqm, min(areas), max(areas)), 4
                )
            else:
                penalty += 0.05

            if listing.lease_remaining_years is not None and leases:
                factors["lease_remaining"] = round(
                    _normalize(listing.lease_remaining_years, min(leases), max(leases)), 4
                )

            if listing.published_at is not None:
                # Freshness placeholder: newer publish dates score higher via ordinal rank.
                factors["freshness"] = 0.5

            utility = sum(weights.get(k, 0.0) * v for k, v in factors.items()) - penalty
            reasons = _build_reasons(listing, factors, profile)
            scored.append(
                RankedItem(
                    listing_id=listing.listing_id,
                    rank=0,
                    score=round(utility, 4),
                    reasons=reasons,
                    factors=factors,
                )
            )

        scored.sort(key=lambda item: item.score, reverse=True)
        diversified = self._diversify(scored, listings, limit)
        for idx, item in enumerate(diversified, start=1):
            item.rank = idx
        return diversified

    @staticmethod
    def _diversify(
        scored: list[RankedItem], listings: list[PropertyListing], limit: int
    ) -> list[RankedItem]:
        by_id = {listing_.listing_id: listing_ for listing_ in listings}
        selected: list[RankedItem] = []
        seen_towns: set[str] = set()
        remaining = list(scored)

        # First pass: best listing per distinct town, to avoid five near-duplicates.
        for item in list(remaining):
            if len(selected) >= limit:
                break
            town = (by_id[item.listing_id].town or "").upper()
            if town and town not in seen_towns:
                selected.append(item)
                seen_towns.add(town)
                remaining.remove(item)

        # Second pass: fill any remaining slots by score.
        for item in remaining:
            if len(selected) >= limit:
                break
            selected.append(item)

        selected.sort(key=lambda item: item.score, reverse=True)
        return selected[:limit]


def _build_reasons(listing: PropertyListing, factors: dict[str, float], profile: BuyerProfile) -> list[str]:
    reasons = []
    if factors.get("affordability_headroom", 0) > 0.1:
        reasons.append("within budget")
    if factors.get("commute_convenience", 0) > 0.6:
        reasons.append("good MRT proximity")
    if factors.get("floor_area", 0) > 0.6:
        reasons.append("spacious relative to shortlist")
    if factors.get("lease_remaining", 0) > 0.6:
        reasons.append("longer remaining lease")
    if listing.town and profile.preferred_towns and listing.town.upper() in {
        t.upper() for t in profile.preferred_towns
    }:
        reasons.append(f"located in preferred town {listing.town}")
    return reasons or ["meets your hard requirements"]
