"""Tests for ``GET/POST /configurations/templates``."""

from __future__ import annotations

import uuid

from httpx import AsyncClient

from app.models.enums import ConfigurationType
from tests.conftest import AuthHeadersFn


async def test_create_and_list_templates(client: AsyncClient, auth_headers: AuthHeadersFn) -> None:
    org_id = uuid.uuid4()
    create_response = await client.post(
        "/configurations/templates",
        json={
            "organization_id": str(org_id),
            "template_name": "nginx-base",
            "configuration_type": ConfigurationType.APPLICATION.value,
            "content": "server { listen 80; }",
        },
        headers=auth_headers(uuid.uuid4()),
    )
    assert create_response.status_code == 201

    list_response = await client.get(
        "/configurations/templates",
        params={"organization_id": str(org_id)},
        headers=auth_headers(uuid.uuid4()),
    )
    assert list_response.status_code == 200
    assert len(list_response.json()["data"]) == 1
    assert list_response.json()["data"][0]["template_name"] == "nginx-base"


async def test_list_templates_filters_by_configuration_type(
    client: AsyncClient, auth_headers: AuthHeadersFn
) -> None:
    org_id = uuid.uuid4()
    await client.post(
        "/configurations/templates",
        json={
            "organization_id": str(org_id),
            "template_name": "app-template",
            "configuration_type": ConfigurationType.APPLICATION.value,
            "content": "x",
        },
        headers=auth_headers(uuid.uuid4()),
    )
    await client.post(
        "/configurations/templates",
        json={
            "organization_id": str(org_id),
            "template_name": "db-template",
            "configuration_type": ConfigurationType.DATABASE.value,
            "content": "y",
        },
        headers=auth_headers(uuid.uuid4()),
    )

    response = await client.get(
        "/configurations/templates",
        params={
            "organization_id": str(org_id),
            "configuration_type": ConfigurationType.DATABASE.value,
        },
        headers=auth_headers(uuid.uuid4()),
    )
    assert response.status_code == 200
    assert len(response.json()["data"]) == 1
    assert response.json()["data"][0]["template_name"] == "db-template"
