"""UI profile <-> canonical ``BuyerProfile``.

The UI's four "must-have" controls (budget, property type, towns, bedrooms) are always hard
filters; its four sliders are the soft weights. "Nothing selected" is meaningful — it means
nothing passes — so empty type/town lists are mapped to sentinels that match no listing instead
of the domain model's "no constraint".
"""

from __future__ import annotations

from app.domain.entities import BuyerProfile
from app.domain.enums import PropertyType
from app.schemas.journey import UIProfile
from app.services.journey_ranker import normalise_weights

HARD_FIELDS = ["max_price_sgd", "min_bedrooms", "preferred_towns", "property_type"]
_NO_TOWN = "__none_selected__"
_TYPE_MAP = {
    "HDB": [PropertyType.HDB],
    "Condo": [PropertyType.CONDO, PropertyType.EC],
}


def ui_to_buyer(session_id: str, ui: UIProfile) -> BuyerProfile:
    types: list[PropertyType] = []
    for name in ui.types:
        types.extend(_TYPE_MAP.get(name, []))
    return BuyerProfile(
        session_id=session_id,
        max_price_sgd=ui.budget if ui.budget > 0 else 1.0,
        property_types=types or [PropertyType.LANDED],  # LANDED is out of scope -> matches nothing
        min_bedrooms=ui.min_bed,
        preferred_towns=[t for t in ui.towns if t] or [_NO_TOWN],
        hard_constraints=list(HARD_FIELDS),
        soft_weights=normalise_weights(ui.weights),
    )


def buyer_to_ui(profile: BuyerProfile | None) -> UIProfile:
    if profile is None:
        return UIProfile()
    types: list[str] = []
    for ptype in {getattr(t, "value", t) for t in [profile.property_type, *profile.property_types] if t}:
        label = "HDB" if ptype == "HDB" else "Condo" if ptype in {"CONDO", "EC"} else None
        if label and label not in types:
            types.append(label)
    towns = [t.title() for t in profile.preferred_towns if t != _NO_TOWN]
    return UIProfile(
        budget=profile.max_price_sgd or UIProfile().budget,
        types=types or UIProfile().types,
        towns=towns or UIProfile().towns,
        min_bed=profile.min_bedrooms if profile.min_bedrooms is not None else UIProfile().min_bed,
        weights=normalise_weights(profile.soft_weights),
    )
