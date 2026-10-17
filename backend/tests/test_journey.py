"""The Homerun UI endpoints (``/api/ui/*``) on the fixture inventory seeded as scraper rows.

Fixture facts the assertions rely on (see ``conftest._seed_fixture_inventory``): Tampines HDBs
101/102/103/104/105/109 (105 has no agent), Bedok 106, Punggol 107, an inactive Woodlands 108 and a
Tampines condo 201.
"""

from __future__ import annotations

import pytest

from app.journey.intent import apply_patch, weights_from_text
from app.schemas.journey import UIProfile

TOWNS = ["Bishan", "Tampines", "Queenstown", "Jurong West", "Punggol"]


def profile(**overrides) -> dict:
    base = {
        "budget": 800_000, "types": ["HDB", "Condo"], "towns": ["Tampines"], "min_bed": 3,
        "weights": {"commute": 8, "mrt": 5, "area": 3, "price": 3},
    }
    return {**base, **overrides}


def match(client, sid: str, **overrides) -> dict:
    response = client.post(
        "/api/ui/match", json={"session_id": sid, "profile": profile(**overrides)}
    )
    assert response.status_code == 200, response.text
    return response.json()


# --- config -----------------------------------------------------------------------------------


def test_config_exposes_ui_towns_and_defaults(client):
    body = client.get("/api/ui/config").json()
    assert body["popular_towns"] == TOWNS and set(TOWNS) <= set(body["towns"])
    assert body["defaults"]["budget"] == 900_000
    assert set(body["defaults"]["weights"]) == {"commute", "mrt", "area", "price"}
    assert body["workplace"] == "Raffles Place"


# --- match ------------------------------------------------------------------------------------


def test_match_filters_ranks_and_explains(client):
    body = match(client, "j-match")
    counts = body["counts"]
    assert counts["checked"] == 9  # 10 fixtures minus the inactive one
    assert counts["eligible"] == 5  # 101, 102, 104, 105, 109 (103 is over budget)
    assert counts["checked"] == counts["eligible"] + counts["excluded"]
    assert body["source_mode"] == "live_scraped"

    ranked = body["ranked"]
    assert len(ranked) == 5
    assert [r["score"] for r in ranked] == sorted((r["score"] for r in ranked), reverse=True)
    first = ranked[0]
    assert {f["k"] for f in first["factors"]} == {"commute", "mrt", "area", "price"}
    assert abs(sum(f["max"] for f in first["factors"]) - 1) < 0.01
    listing = first["listing"]
    assert listing["town"] == "Tampines" and listing["cat"] == "HDB"
    assert listing["val"] is not None  # HDB is valued, with a range around the estimate
    assert listing["val"]["lo"] <= listing["val"]["pt"] <= listing["val"]["hi"]
    assert 1 <= len(first["reasons"]) <= 3

    names = {t["agent_name"] for t in body["trace"]}
    assert {"market_intelligence", "matching_decision", "valuation"} <= names


def test_match_excluded_reasons_use_the_ui_wording(client):
    body = match(client, "j-excl")
    why = {e["id"]: e["why"] for e in body["excluded"]}
    assert why["fixture-103"] == "$20k over"
    assert why["fixture-106"] == "other town"
    assert why["fixture-201"] == "Condo off" or why["fixture-201"].endswith("over")


def test_nothing_selected_means_nothing_passes(client):
    assert match(client, "j-none", towns=[])["counts"]["eligible"] == 0
    assert match(client, "j-none2", types=[])["counts"]["eligible"] == 0


def test_unknown_values_are_penalised_not_best_cased(client):
    ranked = match(client, "j-unk")["ranked"]
    unknown = [r for r in ranked if any(f["s"] is None for f in r["factors"])]
    assert unknown, "fixtures carry no MRT text, so every ranked home has an unknown factor"
    assert all(r["penalty"] > 0 for r in unknown)


# --- chat -------------------------------------------------------------------------------------


EXAMPLE = (
    "3-bedroom under $900k near an MRT, in Bishan, Tampines or Queenstown. "
    "Short commute to Raffles Place matters more than size."
)


def test_chat_extracts_and_asks_only_for_the_missing_type(client):
    body = client.post("/api/ui/chat", json={"session_id": "j-chat", "message": EXAMPLE, "restart": True}).json()
    assert body["stage"] == "ask" and body["asking"] == "type"
    assert body["quick_replies"] == ["HDB only", "Condo only", "Both"]
    assert "≤ $900k" in body["heard"]["must"] and "3+ bedrooms" in body["heard"]["must"]
    assert body["profile"]["budget"] == 900_000 and body["profile"]["min_bed"] == 3
    assert set(body["profile"]["towns"]) == {"Bishan", "Tampines", "Queenstown"}
    w = body["profile"]["weights"]
    assert w["commute"] > w["area"], "'commute matters more than size' must show in the sliders"
    assert any(c["cat"] == "ask" for c in body["chips"])


def test_chat_keeps_asking_until_every_answer_is_in(client):
    def say(msg, **kw):
        return client.post("/api/ui/chat", json={"session_id": "j-loop", "message": msg, **kw}).json()

    r = say("I want a nice home", restart=True)
    assert r["asking"] == "budget" and r["stage"] == "ask"
    r = say("Under $800k")
    assert r["asking"] == "bedrooms" and r["profile"]["budget"] == 800_000
    r = say("4 bedrooms")
    assert r["asking"] == "type" and r["profile"]["min_bed"] == 4
    r = say("Condo only")
    assert r["asking"] == "town" and r["profile"]["types"] == ["Condo"]
    assert "Anywhere" in r["quick_replies"]
    r = say("Bishan")
    assert r["stage"] == "done" and r["asking"] is None and r["profile"]["towns"] == ["Bishan"]


def test_chat_restart_forgets_earlier_answers(client):
    client.post("/api/ui/chat", json={"session_id": "j-rs", "message": "Both", "restart": True})
    r = client.post("/api/ui/chat", json={"session_id": "j-rs", "message": "hello", "restart": True}).json()
    assert r["asking"] == "budget"


def test_chat_with_type_stated_skips_the_question(client):
    body = client.post(
        "/api/ui/chat", json={"session_id": "j-chat3", "message": "a 4 room HDB under $700k in Tampines"}
    ).json()
    assert body["stage"] == "done" and body["profile"]["types"] == ["HDB"]


def test_llm_output_is_grounded_in_what_the_buyer_wrote():
    # a model "helpfully" invented a type and a town the buyer never mentioned
    patch = {"property_type": "HDB", "max_price_sgd": 900000, "preferred_towns": ["BISHAN", "PUNGGOL"]}
    ui, heard, _ = apply_patch(UIProfile(), patch, "something near Bishan, budget 900k", TOWNS)
    assert ui.types == ["HDB", "Condo"], "invented property type must not become a must-have"
    assert "type" not in heard.got
    assert ui.towns == ["Bishan"]


def test_unknown_town_is_reported_not_guessed():
    _, _, warnings = apply_patch(UIProfile(), {"preferred_towns": ["WOODLANDS"]}, "in Woodlands please", TOWNS)
    assert any("Woodlands" in w for w in warnings)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("commute matters more than size", {"commute": 9.0, "area": 2.0}),
        ("I want a bigger place", {"area": 7.0}),
        ("close to the MRT", {"mrt": 6.0}),
        ("nothing in particular", {}),
    ],
)
def test_weights_follow_explicit_wording(text, expected):
    got = weights_from_text(text)
    assert {k: got[k] for k in expected} == expected
    assert set(got) <= {"commute", "mrt", "area", "price"}


# --- feedback / finance / compare -------------------------------------------------------------


def test_feedback_nudges_only_tagged_weights_and_keeps_must_haves(client):
    base = match(client, "j-fb")
    a, b = base["ranked_ids"][0], base["ranked_ids"][1]
    body = client.post(
        "/api/ui/feedback",
        json={"session_id": "j-fb", "profile": profile(), "a_id": a, "b_id": b, "pick": 1, "tags": ["area"]},
    ).json()
    assert body["weights"]["area"] == 5.0 and body["weights"]["price"] == 3.0
    assert "Must-haves untouched" in body["banner"]
    assert body["match"]["counts"] == base["counts"]  # feedback never relaxes a hard filter


def test_feedback_without_tags_changes_nothing(client):
    base = match(client, "j-fb2")
    a, b = base["ranked_ids"][:2]
    body = client.post(
        "/api/ui/feedback",
        json={"session_id": "j-fb2", "profile": profile(), "a_id": a, "b_id": b, "pick": 2, "tags": []},
    ).json()
    assert body["weights"] == {k: float(v) for k, v in profile()["weights"].items()}
    assert body["banner"].startswith("Same order")


def test_finance_uses_the_affordability_agent(client):
    body = client.post(
        "/api/ui/finance",
        json={"listing_id": "fixture-101", "down_payment_pct": 25, "annual_rate_pct": 3.0, "years": 25},
    ).json()
    assert body["loan"] == 585_000  # 780k less 25% down
    assert 2_700 < body["monthly"] < 2_900
    assert body["trace"][0]["agent_name"] == "affordability_risk"


def test_compare_marks_the_best_of_each_row_and_summarises(client):
    body = client.post(
        "/api/ui/compare",
        json={"ids": ["fixture-101", "fixture-104"], "down_payment_pct": 25, "annual_rate_pct": 3, "years": 25},
    ).json()
    rows = {r["key"]: r for r in body["rows"]}
    assert rows["price"]["cells"][1]["tag"] == "lowest"  # 104 at $698k beats 101 at $780k
    assert rows["area"]["cells"][0]["tag"] == "most"
    assert body["summary"].startswith("B is $82k cheaper.")
    assert body["listings"][0]["monthly"] > body["listings"][1]["monthly"]


# --- interest + handoff -----------------------------------------------------------------------


def test_interest_reports_listing_and_agent_state(client):
    verified = client.post("/api/ui/interest", json={"session_id": "j-int", "listing_id": "fixture-101"}).json()
    assert verified["still_listed"]["ok"] is True
    assert verified["agent"]["st"] == "verified" and verified["agent"]["name"] == "Mei Lin Tan"
    missing = client.post("/api/ui/interest", json={"session_id": "j-int", "listing_id": "fixture-105"}).json()
    assert missing["agent"]["st"] == "missing" and missing["direct_contact"] is False


def test_handoff_original_listing_redirects_and_is_remembered(client):
    done = client.post(
        "/api/ui/handoff", json={"session_id": "j-hand", "listing_id": "fixture-105"}
    ).json()
    assert done["outcome"] == "redirected" and done["ref"].startswith("req_")
    hub = client.get("/api/ui/hub", params={"session_id": "j-hand"}).json()
    assert [e["kind"] for e in hub["enquiries"]] == ["redirected"]
    assert "fixture-105" in hub["listings"]


def test_direct_enquiry_needs_consent_and_an_authorised_channel(client):
    denied = client.post(
        "/api/ui/handoff",
        json={"session_id": "j-hand2", "listing_id": "fixture-101", "channel": "authorized_direct_lead",
              "consent": True, "fields": ["name"]},
    )
    assert denied.status_code == 403  # direct lead submission is not authorised in this deployment
    assert denied.json()["error"]["code"] == "unauthorized_channel"
    assert client.get("/api/ui/hub", params={"session_id": "j-hand2"}).json()["enquiries"] == []


# --- hub: viewings, checklist, notes, photos ---------------------------------------------------


def test_viewing_lifecycle_is_scoped_to_the_session(client):
    created = client.post(
        "/api/ui/viewings",
        json={"session_id": "j-view", "listing_id": "fixture-101", "at_ms": 1_900_000_000_000},
    ).json()
    vid = created["id"]
    assert created["st"] == "self" and created["check"] == {}

    patched = client.patch(
        f"/api/ui/viewings/{vid}", params={"session_id": "j-view"},
        json={"checks": {"a": True}, "notes": "Corner unit"},
    ).json()
    assert patched["check"] == {"a": True} and patched["notes"] == "Corner unit"
    client.patch(f"/api/ui/viewings/{vid}", params={"session_id": "j-view"}, json={"checks": {"c": True}})

    hub = client.get("/api/ui/hub", params={"session_id": "j-view"}).json()
    assert hub["viewings"][0]["check"] == {"a": True, "c": True}  # merged, not replaced

    other = client.patch(f"/api/ui/viewings/{vid}", params={"session_id": "someone-else"}, json={"notes": "x"})
    assert other.status_code == 404
    bad = client.patch(f"/api/ui/viewings/{vid}", params={"session_id": "j-view"}, json={"checks": {"zz": True}})
    assert bad.status_code == 422

    assert client.delete(f"/api/ui/viewings/{vid}", params={"session_id": "j-view"}).status_code == 204
    assert client.get("/api/ui/hub", params={"session_id": "j-view"}).json()["viewings"] == []


def test_viewing_for_unknown_listing_is_rejected(client):
    response = client.post(
        "/api/ui/viewings", json={"session_id": "j-view2", "listing_id": "nope", "at_ms": 1}
    )
    assert response.status_code == 404


TINY_PNG = (
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


def test_photo_without_a_vision_model_fails_visibly_and_never_invents_observations(client):
    vid = client.post(
        "/api/ui/viewings", json={"session_id": "j-photo", "listing_id": "fixture-101", "at_ms": 2_000_000_000_000}
    ).json()["id"]
    photo = client.post(
        f"/api/ui/viewings/{vid}/photos", params={"session_id": "j-photo"}, json={"image_data_url": TINY_PNG}
    ).json()
    assert photo["status"] == "loading" and photo["obs"] is None
    result = client.post(f"/api/ui/viewings/{vid}/photos/{photo['id']}/analyze", params={"session_id": "j-photo"}).json()
    assert result["status"] == "error" and result["obs"] is None  # no key in tests -> honest error
    stored = client.get("/api/ui/hub", params={"session_id": "j-photo"}).json()["viewings"][0]["photos"][0]
    assert stored["status"] == "error"
    assert client.delete(
        f"/api/ui/viewings/{vid}/photos/{photo['id']}", params={"session_id": "j-photo"}
    ).status_code == 204


# --- admin ingest -----------------------------------------------------------------------------


def _batch(listing_id: str, provider: str = "propertyguru_scraper") -> dict:
    return {
        "listings": [{
            "listing_id": listing_id, "provider": provider, "external_id": listing_id,
            "fetched_at": "2026-10-18T00:00:00", "status": "inactive",  # keeps shared inventory counts stable "transaction_type": "buy",
            "property_type": "HDB", "asking_price_sgd": 500000, "bedrooms": 3, "floor_area_sqm": 80,
            "town": "TAMPINES", "flat_type": "4 ROOM",
        }],
        "deactivate_missing": False,
    }


def test_ingest_requires_the_admin_token(client):
    assert client.post("/api/admin/ingest", json=_batch("ing-1")).status_code == 403
    assert client.post(
        "/api/admin/ingest", json=_batch("ing-1"), headers={"X-Admin-Token": "wrong"}
    ).status_code == 403


def test_ingest_accepts_scraped_listings_only(client):
    ok = client.post("/api/admin/ingest", json=_batch("ing-2"), headers={"X-Admin-Token": "test-admin-token"})
    assert ok.status_code == 200 and ok.json()["ingested"] == 1
    foreign = client.post(
        "/api/admin/ingest", json=_batch("ing-3", provider="demo_fixture"),
        headers={"X-Admin-Token": "test-admin-token"},
    )
    assert foreign.status_code == 403
    assert client.get("/api/ui/listings", params={"ids": "ing-2"}).json()["listings"]["ing-2"]["town"] == "Tampines"


def test_config_offers_every_town_with_nearby_options(client):
    cfg = client.get("/api/ui/config").json()
    assert "Jurong East" in cfg["towns"] and len(cfg["towns"]) >= 24
    assert "Bishan" in cfg["nearby"]["Tampines"] or len(cfg["nearby"]["Tampines"]) >= 5
    assert "Tampines" not in cfg["nearby"]["Tampines"]


def test_chat_accepts_any_town_not_just_the_default_five(client):
    r = client.post(
        "/api/ui/chat",
        json={"session_id": "j-town", "message": "a 4 room HDB under $700k in Jurong East", "restart": True},
    ).json()
    assert r["profile"]["towns"] == ["Jurong East"]
    assert not any("isn't in this version" in w for w in r["warnings"])


def test_search_by_name_returns_listings_with_coordinates(client):
    r = client.get("/api/ui/search", params={"q": "bishan"}).json()
    assert r["query"] == "bishan" and isinstance(r["places"], list)
    assert all(v["lat"] is not None for v in r["listings"])
