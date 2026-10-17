"""End-to-end P0 flow: chat -> preferences -> recommendations -> compare -> feedback, against
the demo fixture catalog (PRD section 17 example buyer session)."""

from __future__ import annotations


def test_chat_extracts_preferences_without_llm(client) -> None:  # noqa: ANN001
    response = client.post(
        "/api/chat",
        json={"message": "Find me a 4-room HDB in Tampines under S$800k, near the MRT."},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["used_llm"] is False
    patch = body["buyer_profile_patch"]
    assert patch["property_type"] == "HDB"
    assert patch["max_price_sgd"] == 800_000
    assert patch["min_bedrooms"] == 4
    assert "TAMPINES" in patch["preferred_towns"]


def test_recommendations_return_ranked_eligible_listings(client, session_id) -> None:  # noqa: ANN001
    response = client.post(
        "/api/recommendations", json={"session_id": session_id, "limit": 5}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["source_mode"] == "demo_fixture"
    assert 1 <= body["returned_count"] <= 5
    for item in body["items"]:
        assert item["rank"] >= 1
        assert item["asking_price_sgd"] <= 800_000


def test_recommendations_without_profile_is_rejected(client) -> None:  # noqa: ANN001
    response = client.post(
        "/api/recommendations", json={"session_id": "brand-new-session-no-profile"}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"


def test_compare_two_listings(client) -> None:  # noqa: ANN001
    response = client.post(
        "/api/compare", json={"listing_ids": ["fixture-101", "fixture-102"]}
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["listings"]) == 2
    assert "asking_price_sgd" in body["differences"]


def test_feedback_updates_weights_and_rerank(client, session_id) -> None:  # noqa: ANN001
    response = client.post(
        "/api/feedback",
        json={
            "session_id": session_id,
            "chosen_id": "fixture-103",  # larger, farther
            "rejected_id": "fixture-101",  # smaller, closer to MRT
            "event_type": "pairwise_choice",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert "floor_area" in body["updated_weights"] or "commute_convenience" in body["updated_weights"]
    assert body["new_run_id"]


def test_condo_never_gets_hdb_valuation(client) -> None:  # noqa: ANN001
    response = client.get("/api/properties/fixture-201")
    assert response.status_code == 200
    body = response.json()
    assert body["property_type"] == "CONDO"
    assert body["valuation_eligible"] is False
