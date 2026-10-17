"""Pytest fixtures. Points the app at an isolated temp SQLite database and the offline
(template LLM, scraper scheduler off) providers before anything imports ``app.main``, so the test
suite never touches the dev database and never makes a network call. The app only reads
scraper-owned inventory, so the fixture files are seeded into the temp DB as scraper rows.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

_tmp_dir = tempfile.mkdtemp(prefix="homerun-tests-")
os.environ["HOMERUN_DATABASE_URL"] = f"sqlite:///{Path(_tmp_dir, 'test.db').as_posix()}"
os.environ["LISTING_PROVIDER"] = "scraped"
os.environ["SCRAPE_ENABLED"] = "false"
os.environ["LLM_PROVIDER"] = "template"
os.environ["GEMINI_API_KEY"] = ""  # no network: photo analysis must report "unavailable"
os.environ["ADMIN_TOKEN"] = "test-admin-token"
os.environ["HOMERUN_DEBUG"] = "true"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def _seed_fixture_inventory() -> None:
    from app.core.config import get_settings
    from app.db.base import SessionLocal
    from app.providers.listing.demo_fixture_provider import DemoFixtureProvider
    from app.repositories.property_repository import PropertyRepository
    from app.scraper.parser import PROVIDER

    fixtures = DemoFixtureProvider(fixtures_dir=get_settings().fixtures_dir)
    db = SessionLocal()
    try:
        repo = PropertyRepository(db)
        repo.upsert_many([l.model_copy(update={"provider": PROVIDER}) for l in fixtures.all_listings()])
        for agent in fixtures.all_agents():
            repo.upsert_agent(agent)
        for link in fixtures.all_links():
            repo.upsert_link(link)
        db.commit()
    finally:
        db.close()


@pytest.fixture(scope="session")
def client() -> TestClient:
    with TestClient(app) as test_client:
        _seed_fixture_inventory()
        yield test_client


@pytest.fixture
def seed_inventory():
    """Re-seed after a test that deactivates or alters the shared scraper-owned inventory."""
    return _seed_fixture_inventory


@pytest.fixture
def session_id(client: TestClient) -> str:
    response = client.put(
        "/api/preferences",
        params={"session_id": "test-session-001"},
        json={
            "transaction_type": "buy",
            "property_type": "HDB",
            "max_price_sgd": 800000,
            "min_bedrooms": 4,
            "preferred_towns": ["Tampines"],
            "hard_constraints": ["max_price_sgd", "min_bedrooms"],
        },
    )
    assert response.status_code == 200
    return "test-session-001"
