"""Shared pytest fixtures for the gateway test suite."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.config.settings import get_settings
from app.core.factory import create_app


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Return a TestClient wrapping a freshly built application instance."""
    get_settings.cache_clear()
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
    get_settings.cache_clear()
