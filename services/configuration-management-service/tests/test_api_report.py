"""Tests for ``GET /configurations/reports``."""

from __future__ import annotations

import uuid

from httpx import AsyncClient

from app.models.enums import ConfigReportType, ConfigurationType, EnvironmentType
from tests.conftest import AuthHeadersFn


async def test_generate_configuration_report(
    client: AsyncClient, auth_headers: AuthHeadersFn
) -> None:
    org_id = uuid.uuid4()
    create_response = await client.post(
        "/configurations",
        json={
            "organization_id": str(org_id),
            "profile_name": "report-target",
            "environment": EnvironmentType.PRODUCTION.value,
            "configuration_type": ConfigurationType.APPLICATION.value,
        },
        headers=auth_headers(uuid.uuid4()),
    )
    profile_id = create_response.json()["data"]["id"]

    response = await client.get(
        "/configurations/reports",
        params={
            "organization_id": str(org_id),
            "report_type": ConfigReportType.CONFIGURATION.value,
            "profile_id": profile_id,
        },
        headers=auth_headers(uuid.uuid4()),
    )
    assert response.status_code == 200
    assert response.json()["data"]["result"]["profile_name"] == "report-target"


async def test_generate_executive_dashboard_report(
    client: AsyncClient, auth_headers: AuthHeadersFn
) -> None:
    org_id = uuid.uuid4()
    response = await client.get(
        "/configurations/reports",
        params={
            "organization_id": str(org_id),
            "report_type": ConfigReportType.EXECUTIVE_DASHBOARD.value,
        },
        headers=auth_headers(uuid.uuid4()),
    )
    assert response.status_code == 200
    assert "total_profiles" in response.json()["data"]["result"]
