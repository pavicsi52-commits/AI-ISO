"""HTTP tests for ``app/api/credentials.py`` (docs/058 "CREDENTIAL MANAGEMENT").

``POST /integrations/credentials`` and ``POST
/integrations/credentials/{id}/rotate`` both declare a ``caller:
CurrentUserId`` parameter and need a Bearer ``Authorization`` header;
``GET /integrations/credentials/{id}`` does not. Connectors are set up
directly through ``make_connector`` (the ``ConnectorService`` fixture,
sharing the same ``db_session`` the ``client`` fixture's app is wired to)
rather than through the connector HTTP routes, since those *do* require a
Bearer token and are already covered elsewhere -- the same convention this
service's own ``test_api_transformations.py``/``test_api_events.py``
already establish.

Real FastAPI app through ``httpx.ASGITransport`` (the ``client`` fixture),
real PostgreSQL underneath.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.models.enums import AuditAction
from app.repositories.governance import ConnectorAuditRepository
from tests.conftest import (
    HTTP_BAD_REQUEST,
    HTTP_CREATED,
    HTTP_NOT_FOUND,
    HTTP_OK,
    HTTP_UNAUTHORIZED,
    KNOWN_SECRET_ID,
)

pytestmark = pytest.mark.asyncio


class TestAssignCredential:
    async def test_assign_needs_auth(
        self, client: AsyncClient, organization_id: uuid.UUID, make_connector
    ) -> None:
        connector = await make_connector()
        resp = await client.post(
            "/integrations/credentials",
            params={"organization_id": str(organization_id)},
            json={
                "connector_id": str(connector.id),
                "credential_type": "api_key",
                "raw_value": "super-secret-value-1",
            },
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_assign_returns_201_with_expected_shape(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_connector
    ) -> None:
        connector = await make_connector()
        resp = await client.post(
            "/integrations/credentials",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={
                "connector_id": str(connector.id),
                "credential_type": "api_key",
                "raw_value": "super-secret-value-2",
            },
        )
        assert resp.status_code == HTTP_CREATED, resp.text
        data = resp.json()["data"]
        assert data["connector_id"] == str(connector.id)
        assert data["credential_type"] == "api_key"
        assert data["status"] == "active"
        assert data["secret_ref"] is None
        assert "encrypted_value" not in data
        assert "raw_value" not in data

    async def test_assign_never_returns_the_raw_plaintext_value_anywhere(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_connector
    ) -> None:
        connector = await make_connector()
        resp = await client.post(
            "/integrations/credentials",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={
                "connector_id": str(connector.id),
                "credential_type": "api_key",
                "raw_value": "a-very-distinctive-plaintext-value",
            },
        )
        assert resp.status_code == HTTP_CREATED, resp.text
        assert "a-very-distinctive-plaintext-value" not in resp.text

    async def test_assign_with_a_secret_ref_stores_only_the_reference(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_connector
    ) -> None:
        connector = await make_connector()
        resp = await client.post(
            "/integrations/credentials",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={
                "connector_id": str(connector.id),
                "credential_type": "oauth2",
                "secret_ref": KNOWN_SECRET_ID,
            },
        )
        assert resp.status_code == HTTP_CREATED, resp.text
        data = resp.json()["data"]
        assert data["secret_ref"] == KNOWN_SECRET_ID

    async def test_assign_rejects_neither_secret_ref_nor_raw_value(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_connector
    ) -> None:
        connector = await make_connector()
        resp = await client.post(
            "/integrations/credentials",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"connector_id": str(connector.id), "credential_type": "api_key"},
        )
        assert resp.status_code == HTTP_BAD_REQUEST

    async def test_assign_rejects_both_secret_ref_and_raw_value(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_connector
    ) -> None:
        connector = await make_connector()
        resp = await client.post(
            "/integrations/credentials",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={
                "connector_id": str(connector.id),
                "credential_type": "api_key",
                "secret_ref": KNOWN_SECRET_ID,
                "raw_value": "super-secret-value-3",
            },
        )
        assert resp.status_code == HTTP_BAD_REQUEST

    async def test_assign_returns_404_for_an_unknown_connector(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/integrations/credentials",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={
                "connector_id": str(uuid.uuid4()),
                "credential_type": "api_key",
                "raw_value": "super-secret-value-4",
            },
        )
        assert resp.status_code == HTTP_NOT_FOUND

    async def test_assign_records_an_audit_entry(
        self,
        client: AsyncClient,
        auth_headers,
        organization_id: uuid.UUID,
        make_connector,
        db_session,
    ) -> None:
        connector = await make_connector()
        caller = uuid.uuid4()
        resp = await client.post(
            "/integrations/credentials",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(caller),
            json={
                "connector_id": str(connector.id),
                "credential_type": "api_key",
                "raw_value": "super-secret-value-5",
            },
        )
        credential_id = uuid.UUID(resp.json()["data"]["id"])

        entries = await ConnectorAuditRepository(db_session).list_for_org(organization_id)
        matching = [e for e in entries if e.entity_id == credential_id]
        assert len(matching) == 1
        assert matching[0].action == AuditAction.CREDENTIAL_ASSIGNED
        assert matching[0].actor_id == str(caller)


class TestAssignCredentialTenantIsolation:
    """Regression coverage for the cross-tenant credential-hijack bug class
    found in sibling services (e.g. webhook-service's own
    ``/webhooks/signatures``, this same service's own
    ``/integrations/transformations``): a caller must not be able to
    assign a credential onto a connector belonging to a *different*
    organization just because it knows (or guesses) the connector's id.

    ``assign_credential`` already calls ``connectors.get(organization_id,
    body.connector_id)`` first (``app/api/credentials.py``), which raises
    ``NotFoundError`` -- mapped to 404 -- whenever the connector does not
    belong to the caller's own organization, exactly mirroring
    ``create_transformation``'s own guard in ``app/api/transformations.py``.
    These tests confirm that guard actually holds, end to end over real
    HTTP.
    """

    async def test_assign_rejects_a_connector_belonging_to_another_organization(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_connector
    ) -> None:
        victim_connector = await make_connector(name="victim-connector")
        attacker_org = uuid.uuid4()

        resp = await client.post(
            "/integrations/credentials",
            params={"organization_id": str(attacker_org)},
            headers=auth_headers(uuid.uuid4()),
            json={
                "connector_id": str(victim_connector.id),
                "credential_type": "api_key",
                "raw_value": "attacker-secret-value",
            },
        )

        assert resp.status_code == HTTP_NOT_FOUND

    async def test_the_hijack_attempt_does_not_create_any_row(
        self,
        client: AsyncClient,
        auth_headers,
        organization_id: uuid.UUID,
        make_connector,
        credential_service,
    ) -> None:
        victim_connector = await make_connector(name="victim-connector-2")
        attacker_org = uuid.uuid4()

        resp = await client.post(
            "/integrations/credentials",
            params={"organization_id": str(attacker_org)},
            headers=auth_headers(uuid.uuid4()),
            json={
                "connector_id": str(victim_connector.id),
                "credential_type": "api_key",
                "raw_value": "attacker-secret-value-2",
            },
        )
        assert resp.status_code == HTTP_NOT_FOUND

        rows = await credential_service.list_for_connector(victim_connector.id)
        assert rows == []


class TestGetCredential:
    async def test_get_needs_no_auth(
        self,
        client: AsyncClient,
        organization_id: uuid.UUID,
        make_connector,
        make_credential,
    ) -> None:
        connector = await make_connector()
        credential = await make_credential(connector.id, raw_value="get-secret-value")

        resp = await client.get(
            f"/integrations/credentials/{credential.id}",
            params={"organization_id": str(organization_id)},
        )

        assert resp.status_code == HTTP_OK, resp.text
        data = resp.json()["data"]
        assert data["id"] == str(credential.id)
        assert data["connector_id"] == str(connector.id)

    async def test_get_never_returns_the_raw_plaintext_value(
        self, client: AsyncClient, organization_id: uuid.UUID, make_connector, make_credential
    ) -> None:
        connector = await make_connector()
        credential = await make_credential(
            connector.id, raw_value="another-very-distinctive-plaintext-value"
        )

        resp = await client.get(
            f"/integrations/credentials/{credential.id}",
            params={"organization_id": str(organization_id)},
        )

        assert resp.status_code == HTTP_OK
        assert "another-very-distinctive-plaintext-value" not in resp.text

    async def test_get_returns_404_for_an_unknown_id(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.get(
            f"/integrations/credentials/{uuid.uuid4()}",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_NOT_FOUND

    async def test_get_returns_404_for_a_credential_in_another_organization(
        self, client: AsyncClient, organization_id: uuid.UUID, make_connector, make_credential
    ) -> None:
        connector = await make_connector()
        credential = await make_credential(connector.id)

        resp = await client.get(
            f"/integrations/credentials/{credential.id}",
            params={"organization_id": str(uuid.uuid4())},
        )
        assert resp.status_code == HTTP_NOT_FOUND


class TestRotateCredential:
    async def test_rotate_requires_auth(
        self, client: AsyncClient, organization_id: uuid.UUID, make_connector, make_credential
    ) -> None:
        connector = await make_connector()
        credential = await make_credential(connector.id, raw_value="original-secret-value")

        resp = await client.post(
            f"/integrations/credentials/{credential.id}/rotate",
            params={"organization_id": str(organization_id)},
            json={"raw_value": "rotated-secret-value"},
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_rotate_returns_the_rotated_credential(
        self,
        client: AsyncClient,
        auth_headers,
        organization_id: uuid.UUID,
        make_connector,
        make_credential,
    ) -> None:
        connector = await make_connector()
        credential = await make_credential(connector.id, raw_value="original-secret-value")

        resp = await client.post(
            f"/integrations/credentials/{credential.id}/rotate",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"raw_value": "rotated-secret-value"},
        )

        assert resp.status_code == HTTP_OK, resp.text
        data = resp.json()["data"]
        assert data["id"] == str(credential.id)
        assert data["status"] == "active"
        assert data["last_rotated_at"] is not None

    async def test_rotate_never_returns_either_the_old_or_new_plaintext_value(
        self,
        client: AsyncClient,
        auth_headers,
        organization_id: uuid.UUID,
        make_connector,
        make_credential,
    ) -> None:
        connector = await make_connector()
        credential = await make_credential(connector.id, raw_value="original-plaintext-value")

        resp = await client.post(
            f"/integrations/credentials/{credential.id}/rotate",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"raw_value": "rotated-plaintext-value"},
        )

        assert resp.status_code == HTTP_OK
        assert "original-plaintext-value" not in resp.text
        assert "rotated-plaintext-value" not in resp.text

    async def test_rotate_rejects_an_empty_raw_value(
        self,
        client: AsyncClient,
        auth_headers,
        organization_id: uuid.UUID,
        make_connector,
        make_credential,
    ) -> None:
        """``CredentialRotateRequest.raw_value`` has ``min_length=1``.
        FastAPI's own ``RequestValidationError`` for a body that fails it
        is remapped, like every validation failure application-wide, to
        ``shared_core``'s own ``ValidationError`` -- HTTP 400, not the
        framework's default 422 (see
        ``shared_core.exceptions.handlers.register_exception_handlers``).
        """
        connector = await make_connector()
        credential = await make_credential(connector.id)

        resp = await client.post(
            f"/integrations/credentials/{credential.id}/rotate",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"raw_value": ""},
        )
        assert resp.status_code == HTTP_BAD_REQUEST

    async def test_rotate_returns_404_for_an_unknown_credential(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            f"/integrations/credentials/{uuid.uuid4()}/rotate",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"raw_value": "rotated-secret-value"},
        )
        assert resp.status_code == HTTP_NOT_FOUND

    async def test_rotate_rejects_a_credential_belonging_to_another_organization(
        self,
        client: AsyncClient,
        auth_headers,
        organization_id: uuid.UUID,
        make_connector,
        make_credential,
    ) -> None:
        connector = await make_connector()
        credential = await make_credential(connector.id, raw_value="victim-secret-value")

        resp = await client.post(
            f"/integrations/credentials/{credential.id}/rotate",
            params={"organization_id": str(uuid.uuid4())},
            headers=auth_headers(uuid.uuid4()),
            json={"raw_value": "attacker-secret-value"},
        )
        assert resp.status_code == HTTP_NOT_FOUND

    async def test_rotate_records_an_audit_entry(
        self,
        client: AsyncClient,
        auth_headers,
        organization_id: uuid.UUID,
        make_connector,
        make_credential,
        db_session,
    ) -> None:
        connector = await make_connector()
        credential = await make_credential(connector.id, raw_value="original-secret-value")
        caller = uuid.uuid4()

        resp = await client.post(
            f"/integrations/credentials/{credential.id}/rotate",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(caller),
            json={"raw_value": "rotated-secret-value"},
        )
        assert resp.status_code == HTTP_OK

        entries = await ConnectorAuditRepository(db_session).list_for_org(organization_id)
        matching = [e for e in entries if e.entity_id == credential.id]
        assert len(matching) == 1
        assert matching[0].action == AuditAction.CREDENTIAL_ROTATED
        assert matching[0].actor_id == str(caller)
