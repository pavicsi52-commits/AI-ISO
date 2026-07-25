"""Tests for the five ``POST /discovery/*-scan``/``/discovery/scan``
ad-hoc scan-trigger endpoints against the real app lifespan.

Only covers the REST-layer contract (target/credential/ad-hoc-profile
creation, job queuing) -- see ``tests/test_api_job.py``'s own module
docstring for why job *execution* isn't asserted here.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

from httpx import AsyncClient


async def test_scan_without_profile_id_auto_creates_profile(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    headers = auth_headers(uuid.uuid4())
    org_id = uuid.uuid4()

    response = await client.post(
        "/discovery/scan",
        json={
            "organization_id": str(org_id),
            "address": "192.0.2.50",
            "protocol": "tcp",
            "port": 443,
        },
        headers=headers,
    )
    assert response.status_code == 202, response.text
    job = response.json()["data"]
    assert job["profile_id"] is not None
    assert job["status"] == "queued"
    assert job["total_targets"] == 1


async def test_scan_with_credential_creates_credential_reference(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    headers = auth_headers(uuid.uuid4())
    org_id = uuid.uuid4()

    response = await client.post(
        "/discovery/scan",
        json={
            "organization_id": str(org_id),
            "address": "192.0.2.51",
            "protocol": "ssh",
            "credential": {
                "secret_id": str(uuid.uuid4()),
                "credential_type": "ssh_key",
                "name": f"scan-credential-{uuid.uuid4()}",
                "username": "root",
            },
        },
        headers=headers,
    )
    assert response.status_code == 202, response.text


async def test_network_scan_creates_one_target_per_address_protocol_pair(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    headers = auth_headers(uuid.uuid4())
    org_id = uuid.uuid4()

    response = await client.post(
        "/discovery/network-scan",
        json={
            "organization_id": str(org_id),
            "addresses": ["192.0.2.60", "192.0.2.61"],
            "protocols": ["tcp", "icmp"],
        },
        headers=headers,
    )
    assert response.status_code == 202, response.text
    job = response.json()["data"]
    assert job["total_targets"] == 4
    assert job["mode"] == "full_scan"


async def test_cloud_scan_requires_credential(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    headers = auth_headers(uuid.uuid4())
    response = await client.post(
        "/discovery/cloud-scan",
        json={
            "organization_id": str(uuid.uuid4()),
            "cloud_vendor": "aws",
            "address": "123456789012",
        },
        headers=headers,
    )
    assert response.status_code == 400


async def test_cloud_scan_queues_job(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    headers = auth_headers(uuid.uuid4())
    response = await client.post(
        "/discovery/cloud-scan",
        json={
            "organization_id": str(uuid.uuid4()),
            "cloud_vendor": "aws",
            "address": "123456789012",
            "credential": {
                "secret_id": str(uuid.uuid4()),
                "credential_type": "api_key",
                "name": f"cloud-credential-{uuid.uuid4()}",
            },
        },
        headers=headers,
    )
    assert response.status_code == 202, response.text
    assert response.json()["data"]["total_targets"] == 1


async def test_kubernetes_scan_queues_job(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    headers = auth_headers(uuid.uuid4())
    response = await client.post(
        "/discovery/kubernetes-scan",
        json={
            "organization_id": str(uuid.uuid4()),
            "address": "https://cluster.example.internal:6443",
        },
        headers=headers,
    )
    assert response.status_code == 202, response.text


async def test_industrial_scan_queues_job(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    headers = auth_headers(uuid.uuid4())
    response = await client.post(
        "/discovery/industrial-scan",
        json={"organization_id": str(uuid.uuid4()), "addresses": ["192.0.2.70"]},
        headers=headers,
    )
    assert response.status_code == 202, response.text
    assert response.json()["data"]["total_targets"] == 3
