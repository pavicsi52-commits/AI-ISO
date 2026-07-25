"""Tests for ``GET /configurations/analytics``."""

from __future__ import annotations

import uuid

from httpx import AsyncClient

from app.models.enums import ConfigurationType, EnvironmentType
from tests.conftest import AuthHeadersFn


async def test_get_analytics_computes_snapshot(
    client: AsyncClient, auth_headers: AuthHeadersFn
) -> None:
    org_id = uuid.uuid4()
    await client.post(
        "/configurations",
        json={
            "organization_id": str(org_id),
            "profile_name": "analytics-target",
            "environment": EnvironmentType.PRODUCTION.value,
            "configuration_type": ConfigurationType.APPLICATION.value,
        },
        headers=auth_headers(uuid.uuid4()),
    )

    response = await client.get(
        "/configurations/analytics",
        params={"organization_id": str(org_id)},
        headers=auth_headers(uuid.uuid4()),
    )
    assert response.status_code == 200
    assert response.json()["data"]["total_profiles"] == 1
