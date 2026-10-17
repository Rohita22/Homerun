"""Pytest fixtures. Points the app at an isolated temp SQLite database and the offline
(demo fixture / template LLM) providers before anything imports ``app.main``, so the test suite
never touches the dev database and never makes a network call.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

_tmp_dir = tempfile.mkdtemp(prefix="homerun-tests-")
os.environ["HOMERUN_DATABASE_URL"] = f"sqlite:///{Path(_tmp_dir, 'test.db').as_posix()}"
os.environ["LISTING_PROVIDER"] = "demo_fixture"
os.environ["LLM_PROVIDER"] = "template"
os.environ["HOMERUN_DEBUG"] = "true"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


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
