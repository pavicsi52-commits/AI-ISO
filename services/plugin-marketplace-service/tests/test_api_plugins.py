"""HTTP-level tests for ``app/api/plugins.py`` (``/plugins``, the fifteen
literal docs/059 endpoints plus the manifest-submission and
dependency-declaration extensions those endpoints require to work end
to end).
"""

from __future__ import annotations

import hashlib
import json
import uuid

from httpx import AsyncClient

from tests.conftest import (
    HTTP_BAD_REQUEST,
    HTTP_CONFLICT,
    HTTP_CREATED,
    HTTP_NOT_FOUND,
    HTTP_OK,
    AuthHeadersFn,
)


def _manifest(version: str = "1.0.0") -> dict:
    manifest = {
        "name": "API Test Plugin",
        "publisher": "api-tests",
        "category": "utilities",
        "type": "custom_plugin",
        "version": version,
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


async def _register(
    client: AsyncClient, organization_id: uuid.UUID, auth_headers: AuthHeadersFn, *, slug: str
) -> dict:
    response = await client.post(
        "/plugins",
        params={"organization_id": str(organization_id)},
        json={"slug": slug, "name": slug, "category": "utilities", "plugin_type": "custom_plugin"},
        headers=auth_headers(uuid.uuid4()),
    )
    assert response.status_code == HTTP_CREATED, response.text
    return response.json()["data"]


async def _register_and_publish(
    client: AsyncClient,
    organization_id: uuid.UUID,
    auth_headers: AuthHeadersFn,
    *,
    slug: str,
    version: str = "1.0.0",
) -> str:
    plugin = await _register(client, organization_id, auth_headers, slug=slug)
    plugin_id = plugin["id"]
    params = {"organization_id": str(organization_id)}

    manifest_response = await client.post(
        f"/plugins/{plugin_id}/manifest",
        params=params,
        json={"version_number": version, "manifest": _manifest(version)},
    )
    assert manifest_response.status_code == HTTP_CREATED, manifest_response.text
    assert manifest_response.json()["data"]["validation_status"] == "valid"

    published = await client.post(
        "/plugins/publish",
        params={**params, "plugin_id": plugin_id},
        json={"version_number": version},
    )
    assert published.status_code == HTTP_OK, published.text
    assert published.json()["data"]["status"] == "published"
    return plugin_id


async def test_register_and_get_plugin(
    client: AsyncClient, organization_id: uuid.UUID, auth_headers: AuthHeadersFn
) -> None:
    plugin = await _register(client, organization_id, auth_headers, slug="register-get")
    fetched = await client.get(
        f"/plugins/{plugin['id']}", params={"organization_id": str(organization_id)}
    )
    assert fetched.status_code == HTTP_OK, fetched.text
    assert fetched.json()["data"]["slug"] == "register-get"


async def test_register_duplicate_slug_fails(
    client: AsyncClient, organization_id: uuid.UUID, auth_headers: AuthHeadersFn
) -> None:
    await _register(client, organization_id, auth_headers, slug="dup-slug")
    dup = await client.post(
        "/plugins",
        params={"organization_id": str(organization_id)},
        json={
            "slug": "dup-slug",
            "name": "dup",
            "category": "utilities",
            "plugin_type": "custom_plugin",
        },
        headers=auth_headers(uuid.uuid4()),
    )
    assert dup.status_code >= HTTP_BAD_REQUEST, dup.text


async def test_get_plugin_not_found(client: AsyncClient, organization_id: uuid.UUID) -> None:
    response = await client.get(
        f"/plugins/{uuid.uuid4()}", params={"organization_id": str(organization_id)}
    )
    assert response.status_code == HTTP_NOT_FOUND


async def test_list_plugins_filters_by_category(
    client: AsyncClient, organization_id: uuid.UUID, auth_headers: AuthHeadersFn
) -> None:
    await _register(client, organization_id, auth_headers, slug="list-filter-a")
    params = {"organization_id": str(organization_id)}

    listed = await client.get("/plugins", params={**params, "category": "utilities"})
    assert listed.status_code == HTTP_OK, listed.text
    assert any(row["slug"] == "list-filter-a" for row in listed.json()["data"])

    empty = await client.get("/plugins", params={**params, "category": "security"})
    assert empty.status_code == HTTP_OK
    assert all(row["slug"] != "list-filter-a" for row in empty.json()["data"])


async def test_update_plugin_metadata(
    client: AsyncClient, organization_id: uuid.UUID, auth_headers: AuthHeadersFn
) -> None:
    plugin = await _register(client, organization_id, auth_headers, slug="update-meta")
    params = {"organization_id": str(organization_id)}

    updated = await client.put(
        f"/plugins/{plugin['id']}",
        params=params,
        json={"description": "Updated description.", "tags": ["a", "b"]},
    )
    assert updated.status_code == HTTP_OK, updated.text
    assert updated.json()["data"]["description"] == "Updated description."
    assert updated.json()["data"]["tags"] == ["a", "b"]


async def test_submit_manifest_valid(
    client: AsyncClient, organization_id: uuid.UUID, auth_headers: AuthHeadersFn
) -> None:
    plugin = await _register(client, organization_id, auth_headers, slug="manifest-valid")
    response = await client.post(
        f"/plugins/{plugin['id']}/manifest",
        params={"organization_id": str(organization_id)},
        json={"version_number": "1.0.0", "manifest": _manifest()},
    )
    assert response.status_code == HTTP_CREATED, response.text
    assert response.json()["data"]["validation_status"] == "valid"
    assert response.json()["data"]["validation_errors"] == []


async def test_submit_manifest_invalid_reports_errors(
    client: AsyncClient, organization_id: uuid.UUID, auth_headers: AuthHeadersFn
) -> None:
    plugin = await _register(client, organization_id, auth_headers, slug="manifest-invalid")
    response = await client.post(
        f"/plugins/{plugin['id']}/manifest",
        params={"organization_id": str(organization_id)},
        json={"version_number": "1.0.0", "manifest": {"name": ""}},
    )
    assert response.status_code == HTTP_CREATED, response.text
    assert response.json()["data"]["validation_status"] == "invalid"
    assert len(response.json()["data"]["validation_errors"]) > 0


async def test_publish_never_submitted_version_fails(
    client: AsyncClient, organization_id: uuid.UUID, auth_headers: AuthHeadersFn
) -> None:
    plugin = await _register(client, organization_id, auth_headers, slug="publish-never-submitted")
    response = await client.post(
        "/plugins/publish",
        params={"organization_id": str(organization_id), "plugin_id": plugin["id"]},
        json={"version_number": "9.9.9"},
    )
    assert response.status_code >= HTTP_BAD_REQUEST, response.text


async def test_publish_success_moves_plugin_to_published(
    client: AsyncClient, organization_id: uuid.UUID, auth_headers: AuthHeadersFn
) -> None:
    plugin_id = await _register_and_publish(
        client, organization_id, auth_headers, slug="publish-success"
    )
    fetched = await client.get(
        f"/plugins/{plugin_id}", params={"organization_id": str(organization_id)}
    )
    assert fetched.json()["data"]["status"] == "published"
    assert fetched.json()["data"]["current_version_number"] == "1.0.0"


async def test_list_versions(
    client: AsyncClient, organization_id: uuid.UUID, auth_headers: AuthHeadersFn
) -> None:
    plugin_id = await _register_and_publish(
        client, organization_id, auth_headers, slug="list-versions"
    )
    versions = await client.get(
        f"/plugins/{plugin_id}/versions", params={"organization_id": str(organization_id)}
    )
    assert versions.status_code == HTTP_OK, versions.text
    assert len(versions.json()["data"]) == 1
    assert versions.json()["data"][0]["version_number"] == "1.0.0"


async def test_dependencies_declare_and_list(
    client: AsyncClient, organization_id: uuid.UUID, auth_headers: AuthHeadersFn
) -> None:
    plugin_a = await _register_and_publish(client, organization_id, auth_headers, slug="dep-a")
    plugin_b = await _register_and_publish(client, organization_id, auth_headers, slug="dep-b")
    params = {"organization_id": str(organization_id)}

    declared = await client.post(
        f"/plugins/{plugin_b}/dependencies",
        params=params,
        json={"depends_on_plugin_id": plugin_a},
    )
    assert declared.status_code == HTTP_CREATED, declared.text

    listed = await client.get(f"/plugins/{plugin_b}/dependencies", params=params)
    assert listed.status_code == HTTP_OK, listed.text
    assert len(listed.json()["data"]) == 1
    assert listed.json()["data"][0]["depends_on_plugin_id"] == plugin_a


async def test_declaring_a_cyclic_dependency_conflicts(
    client: AsyncClient, organization_id: uuid.UUID, auth_headers: AuthHeadersFn
) -> None:
    plugin_a = await _register_and_publish(client, organization_id, auth_headers, slug="cycle-a")
    plugin_b = await _register_and_publish(client, organization_id, auth_headers, slug="cycle-b")
    params = {"organization_id": str(organization_id)}

    forward = await client.post(
        f"/plugins/{plugin_b}/dependencies", params=params, json={"depends_on_plugin_id": plugin_a}
    )
    assert forward.status_code == HTTP_CREATED, forward.text

    backward = await client.post(
        f"/plugins/{plugin_a}/dependencies", params=params, json={"depends_on_plugin_id": plugin_b}
    )
    assert backward.status_code == HTTP_CONFLICT, backward.text


async def test_install_activate_disable_lifecycle(
    client: AsyncClient, organization_id: uuid.UUID, auth_headers: AuthHeadersFn
) -> None:
    plugin_id = await _register_and_publish(
        client, organization_id, auth_headers, slug="install-lifecycle"
    )
    params = {"organization_id": str(organization_id)}

    installed = await client.post(f"/plugins/{plugin_id}/install", params=params, json={})
    assert installed.status_code == HTTP_CREATED, installed.text
    assert installed.json()["data"]["status"] == "installed"

    activated = await client.post(f"/plugins/{plugin_id}/activate", params=params)
    assert activated.status_code == HTTP_OK, activated.text
    assert activated.json()["data"]["status"] == "active"

    disabled = await client.post(f"/plugins/{plugin_id}/disable", params=params)
    assert disabled.status_code == HTTP_OK, disabled.text
    assert disabled.json()["data"]["status"] == "disabled"


async def test_install_without_published_version_fails(
    client: AsyncClient, organization_id: uuid.UUID, auth_headers: AuthHeadersFn
) -> None:
    plugin = await _register(client, organization_id, auth_headers, slug="install-no-version")
    response = await client.post(
        f"/plugins/{plugin['id']}/install",
        params={"organization_id": str(organization_id)},
        json={},
    )
    assert response.status_code >= HTTP_BAD_REQUEST, response.text


async def test_upgrade_and_rollback(
    client: AsyncClient, organization_id: uuid.UUID, auth_headers: AuthHeadersFn
) -> None:
    plugin_id = await _register_and_publish(
        client, organization_id, auth_headers, slug="upgrade-rollback"
    )
    params = {"organization_id": str(organization_id)}
    installed = await client.post(f"/plugins/{plugin_id}/install", params=params, json={})
    assert installed.status_code == HTTP_CREATED, installed.text

    manifest_v2 = await client.post(
        f"/plugins/{plugin_id}/manifest",
        params=params,
        json={"version_number": "1.1.0", "manifest": _manifest("1.1.0")},
    )
    assert manifest_v2.status_code == HTTP_CREATED, manifest_v2.text
    published_v2 = await client.post(
        "/plugins/publish",
        params={**params, "plugin_id": plugin_id},
        json={"version_number": "1.1.0"},
    )
    assert published_v2.status_code == HTTP_OK, published_v2.text

    upgraded = await client.post(
        f"/plugins/{plugin_id}/upgrade", params=params, json={"to_version_number": "1.1.0"}
    )
    assert upgraded.status_code == HTTP_OK, upgraded.text
    assert upgraded.json()["data"]["installed_version_number"] == "1.1.0"

    rolled_back = await client.post(
        f"/plugins/{plugin_id}/rollback",
        params=params,
        json={"to_version_number": "1.0.0", "reason": "regression"},
    )
    assert rolled_back.status_code == HTTP_OK, rolled_back.text
    assert rolled_back.json()["data"]["installed_version_number"] == "1.0.0"


async def test_archive_plugin(
    client: AsyncClient, organization_id: uuid.UUID, auth_headers: AuthHeadersFn
) -> None:
    plugin = await _register(client, organization_id, auth_headers, slug="archive-me")
    archived = await client.delete(
        f"/plugins/{plugin['id']}",
        params={"organization_id": str(organization_id)},
        headers=auth_headers(uuid.uuid4()),
    )
    assert archived.status_code == HTTP_OK, archived.text
    assert archived.json()["data"]["status"] == "archived"


async def test_marketplace_search_returns_only_published_listings(
    client: AsyncClient,
) -> None:
    response = await client.get("/plugins/marketplace", params={"query": "zz-no-such-plugin-zz"})
    assert response.status_code == HTTP_OK, response.text
    assert response.json()["data"] == []


async def test_reviews_submit_and_list(
    client: AsyncClient, organization_id: uuid.UUID, auth_headers: AuthHeadersFn
) -> None:
    plugin_id = await _register_and_publish(
        client, organization_id, auth_headers, slug="review-plugin"
    )
    submitted = await client.post(
        "/plugins/reviews",
        params={"organization_id": str(organization_id), "plugin_id": plugin_id},
        json={"reviewer_id": "reviewer-1", "rating": 4, "body": "Solid."},
    )
    assert submitted.status_code == HTTP_CREATED, submitted.text

    listed = await client.get("/plugins/reviews", params={"plugin_id": plugin_id})
    assert listed.status_code == HTTP_OK, listed.text
    assert len(listed.json()["data"]) == 1
    assert listed.json()["data"][0]["rating"] == 4


async def test_reviews_invalid_rating_rejected(
    client: AsyncClient, organization_id: uuid.UUID, auth_headers: AuthHeadersFn
) -> None:
    plugin_id = await _register_and_publish(
        client, organization_id, auth_headers, slug="review-bad-rating"
    )
    response = await client.post(
        "/plugins/reviews",
        params={"organization_id": str(organization_id), "plugin_id": plugin_id},
        json={"reviewer_id": "reviewer-1", "rating": 9},
    )
    assert response.status_code >= HTTP_BAD_REQUEST, response.text


async def test_statistics_dashboard(
    client: AsyncClient, organization_id: uuid.UUID, auth_headers: AuthHeadersFn
) -> None:
    await _register(client, organization_id, auth_headers, slug="stats-plugin")
    response = await client.get(
        "/plugins/statistics", params={"organization_id": str(organization_id)}
    )
    assert response.status_code == HTTP_OK, response.text
    assert "latest_window" in response.json()["data"]


async def test_reports_generate_and_list(
    client: AsyncClient, organization_id: uuid.UUID, auth_headers: AuthHeadersFn
) -> None:
    await _register(client, organization_id, auth_headers, slug="report-plugin")
    params = {"organization_id": str(organization_id)}

    generated = await client.post(
        "/plugins/reports",
        params={**params, "kind": "marketplace"},
        headers=auth_headers(uuid.uuid4()),
    )
    assert generated.status_code == HTTP_CREATED, generated.text
    assert generated.json()["data"]["status"] == "completed"

    listed = await client.get("/plugins/reports", params=params)
    assert listed.status_code == HTTP_OK, listed.text
    assert len(listed.json()["data"]) >= 1
