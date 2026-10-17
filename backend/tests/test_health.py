from fastapi.testclient import TestClient


def test_health_ok(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["listing_provider"] == "scraped"
    # healthy only after a successful scrape run, and tests never scrape
    assert body["listing_provider_healthy"] is False
    assert body["database"] == "ok"


def test_metrics_shape(client: TestClient) -> None:
    client.get("/api/health")
    response = client.get("/api/metrics")
    assert response.status_code == 200
    body = response.json()
    assert "p95_latency_ms" in body
    assert body["request_count"] >= 1
