"""Match / feedback / finance / compare for the Homerun UI.

Every number the screens show comes out of the agent pipeline: Market Intelligence hard-filters
the scraped inventory, the Matching agent ranks with :class:`JourneyRanker`, the Valuation agent
values what is shown, and the Affordability agent prices the mortgage. This service only
sequences those calls and shapes the result (short exclusion reasons, tone-tagged reasons, trace
notes) for the UI.
"""

from __future__ import annotations

from app.agents.affordability_agent import AffordabilityRiskAgent
from app.agents.valuation_agent import ValuationAgent
from app.core.errors import NotFoundError
from app.core.time import utcnow
from app.journey.intent import k
from app.journey.profile import ui_to_buyer
from app.journey.views import in_ui_scope, listing_view
from app.orchestration.orchestrator import OrchestrationResult, RecommendationOrchestrator
from app.repositories.feedback_repository import FeedbackRepository
from app.repositories.property_repository import PropertyRepository
from app.repositories.session_repository import SessionRepository
from app.schemas.common import AgentTraceOut
from app.schemas.journey import FeedbackTurnRequest, UIProfile
from app.services.journey_ranker import normalise_weights

SCRAPER_PROVIDER = "propertyguru_scraper"
MAX_EXCLUDED_LISTED = 30
MAX_DOTS = 24
_TAG_LABEL = {"price": "price", "area": "space", "commute": "commute", "mrt": "MRT"}
# Order the design uses when a listing fails several must-haves: report the first that applies.
_REASON_ORDER = ("property_type", "preferred_towns", "min_bedrooms", "max_price_sgd")


def _short_reason(codes: list[dict], cat: str) -> tuple[str, float]:
    """(UI wording, sort key) for the first failed must-have; smaller sort key = nearer miss."""
    by_field = {c["field"]: c for c in codes}
    for field_name in _REASON_ORDER:
        code = by_field.get(field_name)
        if code is None:
            continue
        unknown = code.get("unknown")
        if field_name == "property_type":
            return f"{cat} off", 3.0
        if field_name == "preferred_towns":
            return ("town unknown" if unknown else "other town"), 2.0
        if field_name == "min_bedrooms":
            return ("bedrooms unknown" if unknown else f"{code.get('value')} bedrooms"), 1.0
        if unknown:
            return "price unknown", 1.0
        return f"{k(code['over'])} over", code["over"] / 1_000_000
    return "not a fit", 9.0


def _tone_reasons(view: dict, profile: UIProfile) -> list[dict]:
    out = [{"tone": "mint", "text": f"{k(profile.budget - view['price'])} under budget"}]
    mrt, commute, area = view["mrt"], view["commute"], view["area"]
    if mrt is not None and mrt <= 10:
        out.append({"tone": "mint", "text": f"{mrt} min to MRT"})
    if commute is not None and commute <= 25:
        out.append({"tone": "mint", "text": f"~{commute} min commute"})
    if area is not None and area >= 90:
        out.append({"tone": "mint", "text": f"{area} m²"})
    if commute is not None and commute > 35:
        out.append({"tone": "butter", "text": f"~{commute} min commute"})
    if mrt is None:
        out.append({"tone": "butter", "text": "MRT unknown"})
    if view["val"] is None:
        out.append({"tone": "soft", "text": "no estimate"})
    return out[:3]


class MatchService:
    def __init__(
        self,
        orchestrator: RecommendationOrchestrator,
        property_repo: PropertyRepository,
        session_repo: SessionRepository,
        feedback_repo: FeedbackRepository,
        affordability_agent: AffordabilityRiskAgent,
        valuation_agent: ValuationAgent,
        source_mode: str,
    ) -> None:
        self._orchestrator = orchestrator
        self._properties = property_repo
        self._sessions = session_repo
        self._feedback = feedback_repo
        self._affordability = affordability_agent
        self._valuation = valuation_agent
        self._source_mode = source_mode

    # ------------------------------------------------------------------ match

    def match(
        self,
        request_id: str,
        session_id: str,
        profile: UIProfile,
        limit: int = 5,
        persist: bool = True,
    ) -> dict:
        buyer = ui_to_buyer(session_id, profile)
        if persist:
            self._sessions.save_profile(buyer)
        result = self._orchestrator.produce_recommendations(
            request_id, buyer, limit=limit, persist=persist,
            scope=in_ui_scope, value_ranked_only=True,
        )
        return self._shape(result, profile)

    def _shape(self, result: OrchestrationResult, profile: UIProfile) -> dict:
        cands = result.candidate_set
        ranked_ids = [item.listing_id for item in result.ranked_items]
        eligible_by_id = {l.listing_id: l for l in cands.eligible}

        checked = len(cands.eligible) + len(cands.excluded) + len(cands.needs_confirmation)
        misses = [(e, False) for e in cands.excluded] + [(c, True) for c in cands.needs_confirmation]
        entries = []
        for miss, _unconfirmed in misses:
            listing = self._properties.get(miss["listing_id"])
            if listing is None:
                continue
            cat = "HDB" if getattr(listing.property_type, "value", listing.property_type) == "HDB" else "Condo"
            why, order = _short_reason(miss.get("codes", []), cat)
            entries.append((order, listing, why))
        entries.sort(key=lambda e: e[0])
        excluded = [
            {"id": l.listing_id, "name": listing_view(l)["name"], "why": why}
            for _, l, why in entries[:MAX_EXCLUDED_LISTED]
        ]

        ranked = []
        for item in result.ranked_items:
            listing = eligible_by_id[item.listing_id]
            view = listing_view(listing, self._properties.get_agent_link(listing.listing_id), item.valuation)
            ranked.append(
                {
                    "listing": view,
                    "score": int(item.score),
                    "factors": item.detail.get("factors", []),
                    "penalty": item.detail.get("penalty", 0.0),
                    "reasons": _tone_reasons(view, profile),
                }
            )

        every_id = sorted([*eligible_by_id, *(m["listing_id"] for m, _ in misses)])
        step = max(1, len(every_id) // MAX_DOTS)
        dots = [
            {"id": i, "ok": i in eligible_by_id}
            for i in every_id[::step][:MAX_DOTS]
        ]

        refreshed = self._properties.latest_fetched_at(SCRAPER_PROVIDER)
        warnings = list(result.warnings)
        no_geo = sum(1 for r in ranked if r["listing"]["coords"] is None)
        if ranked:
            warnings.append("Commute is an estimate to Raffles Place (straight-line, not a routed trip).")
        if no_geo:
            warnings.append(f"{no_geo} ranked listing(s) have no coordinates, so they are not on the map.")
        return {
            "run_id": result.run_id,
            "source_mode": self._source_mode,
            "counts": {
                "checked": checked,
                "eligible": len(cands.eligible),
                "excluded": len(cands.excluded) + len(cands.needs_confirmation),
                "ranked": len(ranked),
            },
            "ranked": ranked,
            "ranked_ids": ranked_ids,
            "excluded": excluded,
            "dots": dots,
            "refreshed_at": refreshed.isoformat() if refreshed else None,
            "server_time": utcnow().isoformat(),
            "warnings": warnings,
            "trace": [t.model_dump() for t in self._trace(result, ranked)],
        }

    @staticmethod
    def _trace(result: OrchestrationResult, ranked: list[dict]) -> list[AgentTraceOut]:
        out = []
        cands = result.candidate_set
        for agent_result in result.trace:
            trace = AgentTraceOut.from_agent_result(agent_result)
            name = agent_result.agent_name
            if name == "market_intelligence":
                total = len(cands.eligible) + len(cands.excluded) + len(cands.needs_confirmation)
                trace.detail = f"{total} records · {len(cands.excluded) + len(cands.needs_confirmation)} filtered"
            elif name == "valuation":
                hdb = sum(1 for r in ranked if r["listing"]["cat"] == "HDB")
                skipped = sum(1 for r in ranked if r["listing"]["cat"] != "HDB")
                trace.detail = f"{hdb} HDB" + (f" · {skipped} condo skipped" if skipped else "")
            elif name == "matching_decision":
                pen = sum(1 for r in ranked if r["penalty"])
                trace.detail = "soft rank" + (f" · {pen} penalty" if pen else "")
            out.append(trace)
        return out

    # --------------------------------------------------------------- feedback

    def feedback(self, request_id: str, req: FeedbackTurnRequest) -> dict:
        weights = normalise_weights(req.profile.weights)
        tags = [t for t in req.tags if t in _TAG_LABEL]
        nudged = dict(weights)
        if req.pick in (0, 1):
            for tag in tags:
                nudged[tag] = min(10.0, nudged[tag] + 2)

        before = self.match(request_id, req.session_id, req.profile, persist=False)
        new_profile = req.profile.model_copy(update={"weights": nudged})
        after = self.match(request_id, req.session_id, new_profile, persist=True)

        if req.pick in (0, 1):
            chosen, rejected = (req.a_id, req.b_id) if req.pick == 0 else (req.b_id, req.a_id)
            self._feedback.record(req.session_id, "pairwise_choice", chosen, rejected)

        moved = next(
            (i for i, (b, a) in enumerate(zip(before["ranked_ids"], after["ranked_ids"])) if a != b),
            None,
        )
        if req.pick not in (0, 1) or not tags or moved is None:
            banner = "Same order — your feedback didn’t change much. Must-haves untouched."
        else:
            name = next(r["listing"]["name"] for r in after["ranked"] if r["listing"]["id"] == after["ranked_ids"][moved])
            banner = (
                f"{name} moved to #{moved + 1} — you weighted "
                f"{' + '.join(_TAG_LABEL[t] for t in tags)} higher. Must-haves untouched."
            )
        return {"weights": nudged, "banner": banner, "match": after}

    # ---------------------------------------------------------------- finance

    def finance(self, request_id: str, listing_id: str, down_pct: float, rate: float, years: int) -> dict:
        listing = self._properties.get(listing_id)
        if listing is None or not listing.asking_price_sgd:
            raise NotFoundError(f"Listing {listing_id} has no asking price.")
        result = self._affordability.run(
            request_id, listing.asking_price_sgd, listing.asking_price_sgd * down_pct / 100, rate, years
        )
        estimate = result.data
        trace = AgentTraceOut.from_agent_result(result)
        trace.detail = "deterministic"
        return {
            "monthly": estimate.monthly_payment_sgd,
            "loan": estimate.loan_principal_sgd,
            "down": estimate.down_payment_sgd,
            "scenarios": estimate.scenarios,
            "assumptions": estimate.assumptions,
            "trace": [trace.model_dump()],
        }

    # ---------------------------------------------------------------- compare

    def compare(self, request_id: str, ids: list[str], down_pct: float, rate: float, years: int) -> dict:
        listings = self._properties.get_by_ids(ids)
        if len(listings) < 2:
            raise NotFoundError("Need at least two known listings to compare.")
        views = []
        for listing in listings:
            val = None
            if getattr(listing.property_type, "value", listing.property_type) == "HDB":
                val = self._valuation.run(request_id, listing).data
            view = listing_view(listing, self._properties.get_agent_link(listing.listing_id), val)
            fin = self._affordability.run(
                request_id, listing.asking_price_sgd or 0, (listing.asking_price_sgd or 0) * down_pct / 100,
                rate, years,
            ).data
            view["monthly"] = round(fin.monthly_payment_sgd) if fin else None
            views.append(view)

        def best(values: list, direction: int) -> int:
            nums = [v for v in values if v is not None]
            if len(nums) < 2:
                return -1
            target = max(nums) if direction > 0 else min(nums)
            return values.index(target) if values.count(target) == 1 else -1

        spec = [  # key, label, getter, best direction (0 = no "best"), tag
            ("type", "type", lambda v: v["type"], 0, ""),
            ("beds", "bedrooms", lambda v: v["beds"], 0, ""),
            ("area", "area", lambda v: v["area"], 1, "most"),
            ("lease", "lease left", lambda v: v["lease"], 0, ""),
            ("price", "asking", lambda v: v["price"], -1, "lowest"),
            ("estimate", "estimate", lambda v: (v["val"]["lo"], v["val"]["hi"]) if v["val"] else None, 0, ""),
            ("monthly", "monthly", lambda v: v["monthly"], -1, "lowest"),
            ("mrt", "MRT", lambda v: v["mrt"], -1, "closest"),
            ("commute", "commute", lambda v: v["commute"], -1, "fastest"),
        ]
        rows = []
        for key, label, getter, direction, tag in spec:
            values = [getter(v) for v in views]
            winner = best(values, direction) if direction else -1
            rows.append({"key": key, "label": label, "cells": [
                {"v": v, "unknown": v is None, "tag": tag if i == winner else ""}
                for i, v in enumerate(values)
            ]})

        a, b = views[0], views[1]
        cheap, other = (a, b) if a["price"] < b["price"] else (b, a)
        parts = [f"{'A' if cheap is a else 'B'} is {k(other['price'] - cheap['price'])} cheaper."]
        if a["commute"] is not None and b["commute"] is not None and a["commute"] != b["commute"]:
            quick = a if a["commute"] < b["commute"] else b
            parts.append(
                f"{'A' if quick is a else 'B'} is {abs(a['commute'] - b['commute'])} min closer to work"
                f"{' too' if quick is cheap else ''}."
            )
        if any(v["val"] is None for v in views):
            parts.append("One has no estimate (condo).")
        if any(v["mrt"] is None for v in views):
            parts.append("One has unknown MRT distance.")
        parts.append("Your call.")
        return {"listings": views, "rows": rows, "summary": " ".join(parts)}
