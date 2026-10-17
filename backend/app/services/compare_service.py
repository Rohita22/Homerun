"""Builds the side-by-side comparison payload (PRD section 4 Compare screen: "Explain
price/size/commute/lease trade-offs"; section 11: "side-by-side attributes, differences,
caveats")."""

from __future__ import annotations

from app.domain.entities import PropertyListing

_COMPARE_FIELDS = [
    "asking_price_sgd",
    "floor_area_sqm",
    "bedrooms",
    "bathrooms",
    "town",
    "lease_remaining_years",
    "tenure",
    "floor_level",
]


class CompareService:
    def build(self, listings: list[PropertyListing]) -> tuple[dict[str, list], list[str]]:
        differences: dict[str, list] = {}
        for field_name in _COMPARE_FIELDS:
            values = [getattr(listing, field_name, None) for listing in listings]
            differences[field_name] = values

        caveats = []
        if any(listing.floor_area_sqm is None for listing in listings):
            caveats.append("One or more listings is missing floor area; comparison is partial.")
        if any(listing.lease_remaining_years is None for listing in listings):
            caveats.append("One or more listings is missing remaining lease information.")
        if len({getattr(l.property_type, "value", l.property_type) for l in listings}) > 1:
            caveats.append(
                "Comparing across property types; HDB valuation estimates do not apply to "
                "non-HDB listings."
            )
        mrt_minutes = [
            (listing.attributes or {}).get("mrt_walk_minutes") for listing in listings
        ]
        if all(m is not None for m in mrt_minutes):
            differences["mrt_walk_minutes"] = mrt_minutes
        else:
            caveats.append("MRT walking distance unknown for one or more listings.")

        return differences, caveats
