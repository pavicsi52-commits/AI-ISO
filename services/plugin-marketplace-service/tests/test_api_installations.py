"""HTTP-level tests for ``app/api/installations.py`` (``/plugins/installations``)."""

from __future__ import annotations

import hashlib
import json
import uuid

from httpx import AsyncClient

from tests.conftest import HTTP_CREATED, HTTP_NOT_FOUND, HTTP_OK, REACHABLE_HTTP_URL, AuthHeadersFn


def _manifest() -> dict:
    manifest = {
        "name": "Installation Test Plugin",
        "publisher": "api-tests",
        "category": "utilities",
        "type": "custom_plugin",
        "version": "1.0.0",
        "entry_points": ["main:run"],
        "supported_platform_versions": [
            {"platform": "aiios", "version_constraint": ">=1.0.0,<2.0.0"}
        ],
        "permissions_required": [],
        "dependencies": [],
        "api_requirements": [],
        "health_checks": [],
    }
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    manifest["checksum"] = hashlib.sha256(canonical).hexdigest()
    return manifest


async def _make_installation(
    client: AsyncClient, organization_id: uuid.UUID, auth_headers: AuthHeadersFn, *, slug: str
) -> str:
    params = {"organization_id": str(organization_id)}
    registered = await client.post(
        "/plugins",
        params=params,
        json={"slug": slug, "name": slug, "category": "utilities", "plugin_type": "custom_plugin"},
        headers=auth_headers(uuid.uuid4()),
    )
    assert registered.status_code == HTTP_CREATED, registered.text
    plugin_id = registered.json()["data"]["id"]

    manifest_response = await client.post(
        f"/plugins/{plugin_id}/manifest",
        params=params,
        json={"version_number": "1.0.0", "manifest": _manifest()},
    )
    assert manifest_response.status_code == HTTP_CREATED, manifest_response.text

    published = await client.post(
        "/plugins/publish",
        params={**params, "plugin_id": plugin_id},
        json={"version_number": "1.0.0"},
    )
    assert published.status_code == HTTP_OK, published.text

    installed = await client.post(f"/plugins/{plugin_id}/install", params=params, json={})
    assert installed.status_code == HTTP_CREATED, installed.text
    return installed.json()["data"]["id"]


async def test_list_installations(
    client: AsyncClient, organization_id: uuid.UUID, auth_headers: AuthHeadersFn
) -> None:
    installation_id = await _make_installation(
        client, organization_id, auth_headers, slug="list-installations"
    )
    listed = await client.get(
        "/plugins/installations", params={"organization_id": str(organization_id)}
    )
    assert listed.status_code == HTTP_OK, listed.text
    assert any(row["id"] == installation_id for row in listed.json()["data"])


async def test_get_installation(
    client: AsyncClient, organization_id: uuid.UUID, auth_headers: AuthHeadersFn
) -> None:
    installation_id = await _make_installation(
        client, organization_id, auth_headers, slug="get-installation"
    )
    response = await client.get(
        f"/plugins/installations/{installation_id}",
        params={"organization_id": str(organization_id)},
    )
    assert response.status_code == HTTP_OK, response.text
    assert response.json()["data"]["id"] == installation_id


async def test_get_installation_not_found(client: AsyncClient, organization_id: uuid.UUID) -> None:
    response = await client.get(
        f"/plugins/installations/{uuid.uuid4()}",
        params={"organization_id": str(organization_id)},
    )
    assert response.status_code == HTTP_NOT_FOUND


async def test_configure_installation(
    client: AsyncClient, organization_id: uuid.UUID, auth_headers: AuthHeadersFn
) -> None:
    installation_id = await _make_installation(
        client, organization_id, auth_headers, slug="configure-installation"
    )
    response = await client.put(
        f"/plugins/installations/{installation_id}/configuration",
        params={"organization_id": str(organization_id)},
        json={"configuration": {"health_check_url": REACHABLE_HTTP_URL}},
    )
    assert response.status_code == HTTP_OK, response.text
    assert response.json()["data"]["configuration"]["health_check_url"] == REACHABLE_HTTP_URL
    assert response.json()["data"]["status"] == "configured"


async def test_remove_installation(
    client: AsyncClient, organization_id: uuid.UUID, auth_headers: AuthHeadersFn
) -> None:
    installation_id = await _make_installation(
        client, organization_id, auth_headers, slug="remove-installation"
    )
    response = await client.delete(
        f"/plugins/installations/{installation_id}",
        params={"organization_id": str(organization_id)},
        headers=auth_headers(uuid.uuid4()),
    )
    assert response.status_code == HTTP_OK, response.text
    assert response.json()["data"]["status"] == "removed"


async def test_permission_request_grant_deny_revoke(
    client: AsyncClient, organization_id: uuid.UUID, auth_headers: AuthHeadersFn
) -> None:
    installation_id = await _make_installation(
        client, organization_id, auth_headers, slug="permission-flow"
    )
    params = {"organization_id": str(organization_id)}

    requested = await client.post(
        f"/plugins/installations/{installation_id}/permissions",
        params=params,
        json={"category": "network", "justification": "Needs outbound calls."},
    )
    assert requested.status_code == HTTP_CREATED, requested.text
    grant_id = requested.json()["data"]["id"]
    assert requested.json()["data"]["status"] == "pending"

    listed = await client.get(f"/plugins/installations/{installation_id}/permissions")
    assert listed.status_code == HTTP_OK, listed.text
    assert len(listed.json()["data"]) == 1

    granted = await client.post(
        f"/plugins/installations/permissions/{grant_id}/grant", json={"decided_by": "admin"}
    )
    assert granted.status_code == HTTP_OK, granted.text
    assert granted.json()["data"]["status"] == "granted"

    revoked = await client.post(
        f"/plugins/installations/permissions/{grant_id}/revoke", json={"decided_by": "admin"}
    )
    assert revoked.status_code == HTTP_OK, revoked.text
    assert revoked.json()["data"]["status"] == "revoked"


async def test_permission_deny(
    client: AsyncClient, organization_id: uuid.UUID, auth_headers: AuthHeadersFn
) -> None:
    installation_id = await _make_installation(
        client, organization_id, auth_headers, slug="permission-deny"
    )
    requested = await client.post(
        f"/plugins/installations/{installation_id}/permissions",
        params={"organization_id": str(organization_id)},
        json={"category": "secrets"},
    )
    assert requested.status_code == HTTP_CREATED, requested.text
    grant_id = requested.json()["data"]["id"]

    denied = await client.post(
        f"/plugins/installations/permissions/{grant_id}/deny", json={"decided_by": "admin"}
    )
    assert denied.status_code == HTTP_OK, denied.text
    assert denied.json()["data"]["status"] == "denied"


async def test_health_list_and_probe(
    client: AsyncClient, organization_id: uuid.UUID, auth_headers: AuthHeadersFn
) -> None:
    installation_id = await _make_installation(
        client, organization_id, auth_headers, slug="health-probe"
    )
    params = {"organization_id": str(organization_id)}

    configured = await client.put(
        f"/plugins/installations/{installation_id}/configuration",
        params=params,
        json={"configuration": {"health_check_url": REACHABLE_HTTP_URL}},
    )
    assert configured.status_code == HTTP_OK, configured.text

    empty_history = await client.get(f"/plugins/installations/{installation_id}/health")
    assert empty_history.status_code == HTTP_OK
    assert empty_history.json()["data"] == []

    probed = await client.post(
        f"/plugins/installations/{installation_id}/health/probe", params=params
    )
    assert probed.status_code == HTTP_OK, probed.text
    assert probed.json()["data"]["status"] == "healthy"

    history = await client.get(f"/plugins/installations/{installation_id}/health")
    assert history.status_code == HTTP_OK, history.text
    assert len(history.json()["data"]) == 1
