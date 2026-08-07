"""HTTP tests for ``/integrations/connectors`` and ``/integrations/categories``.

Both routers live in ``app/api/connectors.py``. ``register``, ``configure``,
``remove``, ``enable``, ``disable``, ``upgrade``, ``rollback``, and ``sync``
declare a ``caller: CurrentUserId`` parameter and need ``Authorization``
headers -- confirmed by reading each route decorator directly, not assumed.
Every other route (list/get/install/test/versions/health/probe/deprecate,
and the categories list) needs no auth. Every route takes ``organization_id``
as a query parameter.

``POST .../test`` only exercises the "structural" fallback path here (no
``endpoint_url``/``host``+``port`` in the connector's own config) -- it needs
no network. ``POST .../probe`` genuinely calls
``shared_core.monitoring.checks.check_http_reachable``/``check_tcp_reachable``,
which build their own internal httpx client and cannot be pointed at a test
double, so those tests point at real already-running infra via the
``REACHABLE_*``/``UNREACHABLE_*`` constants, per this suite's own conftest.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.models.enums import AuditAction, ConnectorCategory
from app.repositories.governance import ConnectorAuditRepository
from tests.conftest import (
    HTTP_BAD_REQUEST,
    HTTP_CREATED,
    HTTP_NOT_FOUND,
    HTTP_OK,
    HTTP_UNAUTHORIZED,
    HTTP_UNPROCESSABLE,
    REACHABLE_HTTP_URL,
    REACHABLE_TCP_HOST,
    REACHABLE_TCP_PORT,
    UNREACHABLE_HTTP_URL,
    UNREACHABLE_TCP_HOST,
    UNREACHABLE_TCP_PORT,
)

pytestmark = pytest.mark.asyncio


async def _register(
    client: AsyncClient,
    organization_id: uuid.UUID,
    headers: dict[str, str],
    *,
    name: str,
    category: str = "custom",
    connector_type: str = "rest_api",
    **extra: object,
) -> str:
    """Register a connector over HTTP and return its id."""
    resp = await client.post(
        "/integrations/connectors",
        params={"organization_id": str(organization_id)},
        headers=headers,
        json={"name": name, "category": category, "connector_type": connector_type, **extra},
    )
    assert resp.status_code == HTTP_CREATED, resp.text
    return resp.json()["data"]["id"]


class TestListConnectors:
    async def test_empty_before_any_registration(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.get(
            "/integrations/connectors", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"] == []

    async def test_finds_a_registered_connector(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        await _register(client, organization_id, headers, name="listed-connector")
        resp = await client.get(
            "/integrations/connectors", params={"organization_id": str(organization_id)}
        )
        names = {row["name"] for row in resp.json()["data"]}
        assert "listed-connector" in names

    async def test_filters_by_category(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        await _register(client, organization_id, headers, name="cloud-one", category="cloud")
        await _register(client, organization_id, headers, name="storage-one", category="storage")

        resp = await client.get(
            "/integrations/connectors",
            params={"organization_id": str(organization_id), "category": "cloud"},
        )
        names = {row["name"] for row in resp.json()["data"]}
        assert "cloud-one" in names
        assert "storage-one" not in names

    async def test_filters_by_status(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        params = {"organization_id": str(organization_id)}
        connector_id = await _register(client, organization_id, headers, name="gets-installed")
        await client.post(
            f"/integrations/connectors/{connector_id}/install", params=params, json={}
        )

        installed = await client.get(
            "/integrations/connectors", params={**params, "status": "installed"}
        )
        ids = {row["id"] for row in installed.json()["data"]}
        assert connector_id in ids

        registered = await client.get(
            "/integrations/connectors", params={**params, "status": "registered"}
        )
        ids_registered = {row["id"] for row in registered.json()["data"]}
        assert connector_id not in ids_registered

    async def test_tenant_isolation(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        await _register(client, organization_id, headers, name="isolated-connector")
        resp = await client.get(
            "/integrations/connectors", params={"organization_id": str(uuid.uuid4())}
        )
        assert resp.json()["data"] == []


class TestGetConnector:
    async def test_finds_a_registered_connector(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        connector_id = await _register(client, organization_id, headers, name="get-target")
        resp = await client.get(
            f"/integrations/connectors/{connector_id}",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"]["id"] == connector_id

    async def test_returns_404_for_a_missing_connector(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.get(
            f"/integrations/connectors/{uuid.uuid4()}",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_NOT_FOUND

    async def test_is_scoped_to_its_organization(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        connector_id = await _register(client, organization_id, headers, name="scoped-connector")
        resp = await client.get(
            f"/integrations/connectors/{connector_id}",
            params={"organization_id": str(uuid.uuid4())},
        )
        assert resp.status_code == HTTP_NOT_FOUND


class TestRegisterConnector:
    async def test_requires_auth(self, client: AsyncClient, organization_id: uuid.UUID) -> None:
        resp = await client.post(
            "/integrations/connectors",
            params={"organization_id": str(organization_id)},
            json={"name": "no-auth-connector", "category": "custom", "connector_type": "rest_api"},
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_returns_the_new_connector(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/integrations/connectors",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={
                "name": "billing-connector",
                "category": "business_applications",
                "connector_type": "netsuite",
                "auth_method": "oauth2",
                "description": "Billing system sync.",
                "owner_id": "team-finance",
                "tags": ["finance", "erp"],
            },
        )
        assert resp.status_code == HTTP_CREATED, resp.text
        data = resp.json()["data"]
        assert data["name"] == "billing-connector"
        assert data["category"] == "business_applications"
        assert data["auth_method"] == "oauth2"
        assert data["description"] == "Billing system sync."
        assert data["owner_id"] == "team-finance"
        assert data["tags"] == ["finance", "erp"]
        assert data["status"] == "registered"
        assert data["enabled"] is False
        assert data["current_version_number"] is None

    async def test_records_an_audit_entry(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, db_session
    ) -> None:
        caller = uuid.uuid4()
        headers = auth_headers(caller)
        connector_id = await _register(client, organization_id, headers, name="audited-connector")
        entries = await ConnectorAuditRepository(db_session).list_for_org(organization_id)
        matching = [e for e in entries if e.entity_id == uuid.UUID(connector_id)]
        assert len(matching) == 1
        assert matching[0].action == AuditAction.CONNECTOR_REGISTERED
        assert matching[0].actor_id == str(caller)

    async def test_missing_name_is_a_bad_request(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/integrations/connectors",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"category": "custom", "connector_type": "rest_api"},
        )
        assert resp.status_code == HTTP_BAD_REQUEST

    async def test_invalid_category_is_a_bad_request(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/integrations/connectors",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"name": "bad-category", "category": "not-a-real-category", "connector_type": "x"},
        )
        assert resp.status_code == HTTP_BAD_REQUEST


class TestConfigureConnector:
    async def test_requires_auth(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        params = {"organization_id": str(organization_id)}
        connector_id = await _register(client, organization_id, headers, name="configure-noauth")
        resp = await client.put(
            f"/integrations/connectors/{connector_id}", params=params, json={"config": {"a": 1}}
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_sets_config_and_moves_to_configured(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        params = {"organization_id": str(organization_id)}
        connector_id = await _register(client, organization_id, headers, name="to-configure")
        resp = await client.put(
            f"/integrations/connectors/{connector_id}",
            params=params,
            headers=headers,
            json={"config": {"endpoint_url": "https://example.com"}},
        )
        assert resp.status_code == HTTP_OK
        data = resp.json()["data"]
        assert data["config"] == {"endpoint_url": "https://example.com"}
        assert data["status"] == "configured"

    async def test_records_an_audit_entry(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, db_session
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        params = {"organization_id": str(organization_id)}
        connector_id = await _register(client, organization_id, headers, name="audit-configure")
        await client.put(
            f"/integrations/connectors/{connector_id}",
            params=params,
            headers=headers,
            json={"config": {"a": 1}},
        )
        entries = await ConnectorAuditRepository(db_session).list_for_org(organization_id)
        matching = [e for e in entries if e.entity_id == uuid.UUID(connector_id)]
        assert AuditAction.CONNECTOR_CONFIGURED in {e.action for e in matching}

    async def test_returns_404_for_a_missing_connector(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        resp = await client.put(
            f"/integrations/connectors/{uuid.uuid4()}",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"config": {}},
        )
        assert resp.status_code == HTTP_NOT_FOUND


class TestRemoveConnector:
    async def test_requires_auth(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        params = {"organization_id": str(organization_id)}
        connector_id = await _register(client, organization_id, headers, name="remove-noauth")
        resp = await client.delete(f"/integrations/connectors/{connector_id}", params=params)
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_marks_removed(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        params = {"organization_id": str(organization_id)}
        connector_id = await _register(client, organization_id, headers, name="to-remove")
        resp = await client.delete(
            f"/integrations/connectors/{connector_id}", params=params, headers=headers
        )
        assert resp.status_code == HTTP_OK
        data = resp.json()["data"]
        assert data["status"] == "removed"
        assert data["enabled"] is False

    async def test_records_an_audit_entry(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, db_session
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        params = {"organization_id": str(organization_id)}
        connector_id = await _register(client, organization_id, headers, name="audit-remove")
        await client.delete(
            f"/integrations/connectors/{connector_id}", params=params, headers=headers
        )
        entries = await ConnectorAuditRepository(db_session).list_for_org(organization_id)
        matching = [e for e in entries if e.entity_id == uuid.UUID(connector_id)]
        assert AuditAction.CONNECTOR_REMOVED in {e.action for e in matching}

    async def test_returns_404_for_a_missing_connector(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        resp = await client.delete(
            f"/integrations/connectors/{uuid.uuid4()}",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
        )
        assert resp.status_code == HTTP_NOT_FOUND


class TestInstallConnector:
    async def test_defaults_to_version_1_0_0(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        params = {"organization_id": str(organization_id)}
        connector_id = await _register(client, organization_id, headers, name="install-default")
        resp = await client.post(
            f"/integrations/connectors/{connector_id}/install", params=params, json={}
        )
        assert resp.status_code == HTTP_OK
        data = resp.json()["data"]
        assert data["current_version_number"] == "1.0.0"
        assert data["status"] == "installed"

    async def test_installs_a_custom_version(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        params = {"organization_id": str(organization_id)}
        connector_id = await _register(client, organization_id, headers, name="install-custom")
        resp = await client.post(
            f"/integrations/connectors/{connector_id}/install",
            params=params,
            json={"version_number": "3.2.1"},
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"]["current_version_number"] == "3.2.1"

    async def test_rejects_a_malformed_version(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        params = {"organization_id": str(organization_id)}
        connector_id = await _register(client, organization_id, headers, name="install-bad-version")
        resp = await client.post(
            f"/integrations/connectors/{connector_id}/install",
            params=params,
            json={"version_number": "not-a-version"},
        )
        assert resp.status_code == HTTP_UNPROCESSABLE

    async def test_returns_404_for_a_missing_connector(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            f"/integrations/connectors/{uuid.uuid4()}/install",
            params={"organization_id": str(organization_id)},
            json={},
        )
        assert resp.status_code == HTTP_NOT_FOUND


class TestTestConnector:
    async def test_structural_failure_with_no_config_and_no_credential(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        params = {"organization_id": str(organization_id)}
        connector_id = await _register(client, organization_id, headers, name="bare-connector")

        resp = await client.post(f"/integrations/connectors/{connector_id}/test", params=params)
        assert resp.status_code == HTTP_OK, resp.text
        data = resp.json()["data"]
        assert data["status"] == "failed"
        assert data["error"] == "Connector has no configuration."
        assert data["connector_id"] == connector_id
        assert data["credential_id"] is None

        found = await client.get(f"/integrations/connectors/{connector_id}", params=params)
        assert found.json()["data"]["status"] != "validated"

    async def test_structural_failure_with_config_but_no_credential(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        params = {"organization_id": str(organization_id)}
        connector_id = await _register(client, organization_id, headers, name="configured-only")
        await client.put(
            f"/integrations/connectors/{connector_id}",
            params=params,
            headers=headers,
            json={"config": {"api_base": "https://example.com/api"}},
        )

        resp = await client.post(f"/integrations/connectors/{connector_id}/test", params=params)
        assert resp.status_code == HTTP_OK
        data = resp.json()["data"]
        assert data["status"] == "failed"
        assert data["error"] == "Connector has no an active credential."

    async def test_structural_success_with_config_and_active_credential(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_credential
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        params = {"organization_id": str(organization_id)}
        connector_id = await _register(client, organization_id, headers, name="fully-set-up")
        await client.put(
            f"/integrations/connectors/{connector_id}",
            params=params,
            headers=headers,
            json={"config": {"api_base": "https://example.com/api"}},
        )
        await make_credential(uuid.UUID(connector_id))

        resp = await client.post(f"/integrations/connectors/{connector_id}/test", params=params)
        assert resp.status_code == HTTP_OK
        data = resp.json()["data"]
        assert data["status"] == "success"
        assert data["error"] is None
        assert data["connector_id"] == connector_id

        found = await client.get(f"/integrations/connectors/{connector_id}", params=params)
        found_data = found.json()["data"]
        assert found_data["status"] == "validated"
        assert found_data["last_validated_at"] is not None

    async def test_returns_404_for_a_missing_connector(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            f"/integrations/connectors/{uuid.uuid4()}/test",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_NOT_FOUND


class TestEnableConnector:
    async def test_requires_auth(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        params = {"organization_id": str(organization_id)}
        connector_id = await _register(client, organization_id, headers, name="enable-noauth")
        resp = await client.post(f"/integrations/connectors/{connector_id}/enable", params=params)
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_enables_the_connector(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        params = {"organization_id": str(organization_id)}
        connector_id = await _register(client, organization_id, headers, name="to-enable")
        resp = await client.post(
            f"/integrations/connectors/{connector_id}/enable", params=params, headers=headers
        )
        assert resp.status_code == HTTP_OK
        data = resp.json()["data"]
        assert data["enabled"] is True
        assert data["status"] == "enabled"

    async def test_records_an_audit_entry(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, db_session
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        params = {"organization_id": str(organization_id)}
        connector_id = await _register(client, organization_id, headers, name="audit-enable")
        await client.post(
            f"/integrations/connectors/{connector_id}/enable", params=params, headers=headers
        )
        entries = await ConnectorAuditRepository(db_session).list_for_org(organization_id)
        matching = [e for e in entries if e.entity_id == uuid.UUID(connector_id)]
        assert AuditAction.CONNECTOR_ENABLED in {e.action for e in matching}

    async def test_returns_404_for_a_missing_connector(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            f"/integrations/connectors/{uuid.uuid4()}/enable",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
        )
        assert resp.status_code == HTTP_NOT_FOUND


class TestDisableConnector:
    async def test_requires_auth(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        params = {"organization_id": str(organization_id)}
        connector_id = await _register(client, organization_id, headers, name="disable-noauth")
        await client.post(
            f"/integrations/connectors/{connector_id}/enable", params=params, headers=headers
        )
        resp = await client.post(f"/integrations/connectors/{connector_id}/disable", params=params)
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_disables_the_connector(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        params = {"organization_id": str(organization_id)}
        connector_id = await _register(client, organization_id, headers, name="to-disable")
        await client.post(
            f"/integrations/connectors/{connector_id}/enable", params=params, headers=headers
        )
        resp = await client.post(
            f"/integrations/connectors/{connector_id}/disable", params=params, headers=headers
        )
        assert resp.status_code == HTTP_OK
        data = resp.json()["data"]
        assert data["enabled"] is False
        assert data["status"] == "disabled"

    async def test_records_an_audit_entry(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, db_session
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        params = {"organization_id": str(organization_id)}
        connector_id = await _register(client, organization_id, headers, name="audit-disable")
        await client.post(
            f"/integrations/connectors/{connector_id}/disable", params=params, headers=headers
        )
        entries = await ConnectorAuditRepository(db_session).list_for_org(organization_id)
        matching = [e for e in entries if e.entity_id == uuid.UUID(connector_id)]
        assert AuditAction.CONNECTOR_DISABLED in {e.action for e in matching}

    async def test_returns_404_for_a_missing_connector(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            f"/integrations/connectors/{uuid.uuid4()}/disable",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
        )
        assert resp.status_code == HTTP_NOT_FOUND


class TestUpgradeConnector:
    async def test_requires_auth(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        params = {"organization_id": str(organization_id)}
        connector_id = await _register(client, organization_id, headers, name="upgrade-noauth")
        await client.post(
            f"/integrations/connectors/{connector_id}/install", params=params, json={}
        )
        resp = await client.post(
            f"/integrations/connectors/{connector_id}/upgrade",
            params=params,
            json={"version_number": "1.1.0"},
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_upgrades_to_a_newer_version(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        params = {"organization_id": str(organization_id)}
        connector_id = await _register(client, organization_id, headers, name="upgrade-target")
        await client.post(
            f"/integrations/connectors/{connector_id}/install", params=params, json={}
        )
        resp = await client.post(
            f"/integrations/connectors/{connector_id}/upgrade",
            params=params,
            headers=headers,
            json={"version_number": "1.1.0"},
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"]["current_version_number"] == "1.1.0"

        versions = await client.get(
            f"/integrations/connectors/{connector_id}/versions", params=params
        )
        by_version = {v["version_number"]: v for v in versions.json()["data"]}
        assert by_version["1.1.0"]["is_current"] is True
        assert by_version["1.0.0"]["is_current"] is False

    async def test_records_an_audit_entry(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, db_session
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        params = {"organization_id": str(organization_id)}
        connector_id = await _register(client, organization_id, headers, name="audit-upgrade")
        await client.post(
            f"/integrations/connectors/{connector_id}/install", params=params, json={}
        )
        await client.post(
            f"/integrations/connectors/{connector_id}/upgrade",
            params=params,
            headers=headers,
            json={"version_number": "1.1.0"},
        )
        entries = await ConnectorAuditRepository(db_session).list_for_org(organization_id)
        matching = [e for e in entries if e.entity_id == uuid.UUID(connector_id)]
        assert AuditAction.CONNECTOR_UPGRADED in {e.action for e in matching}

    async def test_rejects_an_older_version(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        params = {"organization_id": str(organization_id)}
        connector_id = await _register(
            client, organization_id, headers, name="upgrade-reject-older"
        )
        await client.post(
            f"/integrations/connectors/{connector_id}/install",
            params=params,
            json={"version_number": "2.0.0"},
        )
        resp = await client.post(
            f"/integrations/connectors/{connector_id}/upgrade",
            params=params,
            headers=headers,
            json={"version_number": "1.0.0"},
        )
        assert resp.status_code == HTTP_BAD_REQUEST

    async def test_rejects_a_malformed_version(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        params = {"organization_id": str(organization_id)}
        connector_id = await _register(client, organization_id, headers, name="upgrade-bad-version")
        await client.post(
            f"/integrations/connectors/{connector_id}/install", params=params, json={}
        )
        resp = await client.post(
            f"/integrations/connectors/{connector_id}/upgrade",
            params=params,
            headers=headers,
            json={"version_number": "not-a-version"},
        )
        assert resp.status_code == HTTP_UNPROCESSABLE

    async def test_returns_404_for_a_missing_connector(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            f"/integrations/connectors/{uuid.uuid4()}/upgrade",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"version_number": "1.1.0"},
        )
        assert resp.status_code == HTTP_NOT_FOUND


class TestRollbackConnector:
    async def test_requires_auth(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        params = {"organization_id": str(organization_id)}
        connector_id = await _register(client, organization_id, headers, name="rollback-noauth")
        await client.post(
            f"/integrations/connectors/{connector_id}/install",
            params=params,
            json={"version_number": "1.0.0"},
        )
        await client.post(
            f"/integrations/connectors/{connector_id}/upgrade",
            params=params,
            headers=headers,
            json={"version_number": "2.0.0"},
        )
        resp = await client.post(
            f"/integrations/connectors/{connector_id}/rollback",
            params=params,
            json={"version_number": "1.0.0"},
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_rolls_back_to_a_previously_installed_version(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        params = {"organization_id": str(organization_id)}
        connector_id = await _register(client, organization_id, headers, name="rollback-target")
        await client.post(
            f"/integrations/connectors/{connector_id}/install",
            params=params,
            json={"version_number": "1.0.0"},
        )
        await client.post(
            f"/integrations/connectors/{connector_id}/upgrade",
            params=params,
            headers=headers,
            json={"version_number": "2.0.0"},
        )
        resp = await client.post(
            f"/integrations/connectors/{connector_id}/rollback",
            params=params,
            headers=headers,
            json={"version_number": "1.0.0"},
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"]["current_version_number"] == "1.0.0"

    async def test_records_an_audit_entry(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, db_session
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        params = {"organization_id": str(organization_id)}
        connector_id = await _register(client, organization_id, headers, name="audit-rollback")
        await client.post(
            f"/integrations/connectors/{connector_id}/install",
            params=params,
            json={"version_number": "1.0.0"},
        )
        await client.post(
            f"/integrations/connectors/{connector_id}/upgrade",
            params=params,
            headers=headers,
            json={"version_number": "2.0.0"},
        )
        await client.post(
            f"/integrations/connectors/{connector_id}/rollback",
            params=params,
            headers=headers,
            json={"version_number": "1.0.0"},
        )
        entries = await ConnectorAuditRepository(db_session).list_for_org(organization_id)
        matching = [e for e in entries if e.entity_id == uuid.UUID(connector_id)]
        assert AuditAction.CONNECTOR_ROLLED_BACK in {e.action for e in matching}

    async def test_rejects_a_version_never_installed(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        params = {"organization_id": str(organization_id)}
        connector_id = await _register(client, organization_id, headers, name="rollback-reject")
        await client.post(
            f"/integrations/connectors/{connector_id}/install",
            params=params,
            json={"version_number": "2.0.0"},
        )
        resp = await client.post(
            f"/integrations/connectors/{connector_id}/rollback",
            params=params,
            headers=headers,
            json={"version_number": "1.0.0"},
        )
        assert resp.status_code == HTTP_BAD_REQUEST

    async def test_returns_404_for_a_missing_connector(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            f"/integrations/connectors/{uuid.uuid4()}/rollback",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"version_number": "1.0.0"},
        )
        assert resp.status_code == HTTP_NOT_FOUND


class TestDeprecateConnector:
    async def test_marks_deprecated_and_disables(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        params = {"organization_id": str(organization_id)}
        connector_id = await _register(client, organization_id, headers, name="to-deprecate")
        await client.post(
            f"/integrations/connectors/{connector_id}/enable", params=params, headers=headers
        )
        resp = await client.post(
            f"/integrations/connectors/{connector_id}/deprecate", params=params
        )
        assert resp.status_code == HTTP_OK
        data = resp.json()["data"]
        assert data["status"] == "deprecated"
        assert data["enabled"] is False

    async def test_returns_404_for_a_missing_connector(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            f"/integrations/connectors/{uuid.uuid4()}/deprecate",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_NOT_FOUND


class TestListConnectorVersions:
    async def test_empty_before_any_install(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        params = {"organization_id": str(organization_id)}
        connector_id = await _register(client, organization_id, headers, name="no-versions-yet")
        resp = await client.get(f"/integrations/connectors/{connector_id}/versions", params=params)
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"] == []

    async def test_lists_install_and_upgrade_history(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        params = {"organization_id": str(organization_id)}
        connector_id = await _register(client, organization_id, headers, name="versioned")
        await client.post(
            f"/integrations/connectors/{connector_id}/install",
            params=params,
            json={"version_number": "1.0.0"},
        )
        await client.post(
            f"/integrations/connectors/{connector_id}/upgrade",
            params=params,
            headers=headers,
            json={"version_number": "1.1.0"},
        )
        resp = await client.get(f"/integrations/connectors/{connector_id}/versions", params=params)
        version_numbers = {v["version_number"] for v in resp.json()["data"]}
        assert version_numbers == {"1.0.0", "1.1.0"}

    async def test_returns_404_for_a_missing_connector(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.get(
            f"/integrations/connectors/{uuid.uuid4()}/versions",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_NOT_FOUND

    async def test_returns_404_across_tenants(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        connector_id = await _register(client, organization_id, headers, name="cross-org-versions")
        resp = await client.get(
            f"/integrations/connectors/{connector_id}/versions",
            params={"organization_id": str(uuid.uuid4())},
        )
        assert resp.status_code == HTTP_NOT_FOUND


class TestConnectorHealthHistory:
    async def test_empty_before_any_probe(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        params = {"organization_id": str(organization_id)}
        connector_id = await _register(client, organization_id, headers, name="no-probes-yet")
        resp = await client.get(f"/integrations/connectors/{connector_id}/health", params=params)
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"] == []

    async def test_lists_a_recorded_probe(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        params = {"organization_id": str(organization_id)}
        connector_id = await _register(client, organization_id, headers, name="probed")
        await client.put(
            f"/integrations/connectors/{connector_id}",
            params=params,
            headers=headers,
            json={"config": {"host": REACHABLE_TCP_HOST, "port": REACHABLE_TCP_PORT}},
        )
        await client.post(f"/integrations/connectors/{connector_id}/probe", params=params)

        resp = await client.get(f"/integrations/connectors/{connector_id}/health", params=params)
        assert resp.status_code == HTTP_OK
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["status"] == "healthy"

    async def test_returns_404_for_a_missing_connector(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.get(
            f"/integrations/connectors/{uuid.uuid4()}/health",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_NOT_FOUND


class TestProbeConnector:
    async def test_healthy_over_tcp(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        params = {"organization_id": str(organization_id)}
        connector_id = await _register(client, organization_id, headers, name="tcp-reachable")
        await client.put(
            f"/integrations/connectors/{connector_id}",
            params=params,
            headers=headers,
            json={"config": {"host": REACHABLE_TCP_HOST, "port": REACHABLE_TCP_PORT}},
        )

        resp = await client.post(f"/integrations/connectors/{connector_id}/probe", params=params)
        assert resp.status_code == HTTP_OK, resp.text
        data = resp.json()["data"]
        assert data["status"] == "healthy"
        assert data["error"] is None
        assert data["consecutive_failures"] == 0
        assert data["connector_id"] == connector_id

        found = await client.get(f"/integrations/connectors/{connector_id}", params=params)
        found_data = found.json()["data"]
        assert found_data["consecutive_failures"] == 0
        assert found_data["last_health_check_at"] is not None

    async def test_unhealthy_over_tcp_increments_consecutive_failures(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        params = {"organization_id": str(organization_id)}
        connector_id = await _register(client, organization_id, headers, name="tcp-unreachable")
        await client.put(
            f"/integrations/connectors/{connector_id}",
            params=params,
            headers=headers,
            json={"config": {"host": UNREACHABLE_TCP_HOST, "port": UNREACHABLE_TCP_PORT}},
        )

        resp = await client.post(f"/integrations/connectors/{connector_id}/probe", params=params)
        assert resp.status_code == HTTP_OK
        data = resp.json()["data"]
        assert data["status"] == "unhealthy"
        assert data["error"] is not None
        assert data["consecutive_failures"] == 1
        assert data["recovery_attempted"] is False

        found = await client.get(f"/integrations/connectors/{connector_id}", params=params)
        assert found.json()["data"]["consecutive_failures"] == 1

    async def test_healthy_over_http(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        params = {"organization_id": str(organization_id)}
        connector_id = await _register(client, organization_id, headers, name="http-reachable")
        await client.put(
            f"/integrations/connectors/{connector_id}",
            params=params,
            headers=headers,
            json={"config": {"endpoint_url": REACHABLE_HTTP_URL}},
        )

        resp = await client.post(f"/integrations/connectors/{connector_id}/probe", params=params)
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"]["status"] == "healthy"

    async def test_unhealthy_over_http(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        params = {"organization_id": str(organization_id)}
        connector_id = await _register(client, organization_id, headers, name="http-unreachable")
        await client.put(
            f"/integrations/connectors/{connector_id}",
            params=params,
            headers=headers,
            json={"config": {"endpoint_url": UNREACHABLE_HTTP_URL}},
        )

        resp = await client.post(f"/integrations/connectors/{connector_id}/probe", params=params)
        assert resp.status_code == HTTP_OK
        data = resp.json()["data"]
        assert data["status"] == "unhealthy"
        assert data["error"] is not None

    async def test_unknown_with_no_checkable_config(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        params = {"organization_id": str(organization_id)}
        connector_id = await _register(client, organization_id, headers, name="no-config")

        resp = await client.post(f"/integrations/connectors/{connector_id}/probe", params=params)
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"]["status"] == "unknown"

    async def test_returns_404_for_a_missing_connector(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            f"/integrations/connectors/{uuid.uuid4()}/probe",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_NOT_FOUND


class TestSyncConnector:
    async def test_requires_auth(self, client: AsyncClient, organization_id: uuid.UUID) -> None:
        resp = await client.post(
            f"/integrations/connectors/{uuid.uuid4()}/sync",
            params={"organization_id": str(organization_id)},
            json={"records": []},
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_runs_a_sync_job_immediately(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        params = {"organization_id": str(organization_id)}
        connector_id = await _register(client, organization_id, headers, name="sync-target")

        resp = await client.post(
            f"/integrations/connectors/{connector_id}/sync",
            params=params,
            headers=headers,
            json={"records": [{"id": 1}, {"id": 2}, {"id": 3}]},
        )
        assert resp.status_code == HTTP_OK, resp.text
        data = resp.json()["data"]
        assert data["records_succeeded"] == 3
        assert data["records_failed"] == 0
        assert data["records_processed"] == 3
        assert data["status"] == "completed"
        assert data["connector_id"] == connector_id

    async def test_runs_with_no_records(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        params = {"organization_id": str(organization_id)}
        connector_id = await _register(client, organization_id, headers, name="empty-sync")

        resp = await client.post(
            f"/integrations/connectors/{connector_id}/sync",
            params=params,
            headers=headers,
            json={"records": []},
        )
        assert resp.status_code == HTTP_OK
        data = resp.json()["data"]
        assert data["records_succeeded"] == 0
        assert data["records_failed"] == 0
        assert data["status"] == "completed"

    async def test_records_an_audit_entry(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, db_session
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        params = {"organization_id": str(organization_id)}
        connector_id = await _register(client, organization_id, headers, name="audit-sync")
        await client.post(
            f"/integrations/connectors/{connector_id}/sync",
            params=params,
            headers=headers,
            json={"records": [{"id": 1}]},
        )
        entries = await ConnectorAuditRepository(db_session).list_for_org(organization_id)
        matching = [e for e in entries if e.entity_id == uuid.UUID(connector_id)]
        assert AuditAction.SYNC_TRIGGERED in {e.action for e in matching}

    async def test_returns_404_for_a_missing_connector(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            f"/integrations/connectors/{uuid.uuid4()}/sync",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"records": []},
        )
        assert resp.status_code == HTTP_NOT_FOUND


class TestListCategories:
    async def test_seeds_and_returns_all_fifteen_on_first_call(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.get(
            "/integrations/categories", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        data = resp.json()["data"]
        assert len(data) == 15
        names = {row["name"] for row in data}
        assert names == {c.value for c in ConnectorCategory}
        assert all(row["built_in"] for row in data)

    async def test_does_not_duplicate_on_a_second_call(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        params = {"organization_id": str(organization_id)}
        first = await client.get("/integrations/categories", params=params)
        first_ids = {row["id"] for row in first.json()["data"]}
        assert len(first_ids) == 15

        second = await client.get("/integrations/categories", params=params)
        second_ids = {row["id"] for row in second.json()["data"]}
        assert second_ids == first_ids

    async def test_tenant_isolation(self, client: AsyncClient, organization_id: uuid.UUID) -> None:
        await client.get(
            "/integrations/categories", params={"organization_id": str(organization_id)}
        )
        resp = await client.get(
            "/integrations/categories", params={"organization_id": str(uuid.uuid4())}
        )
        # a different org gets its own, independently seeded fifteen
        assert len(resp.json()["data"]) == 15
