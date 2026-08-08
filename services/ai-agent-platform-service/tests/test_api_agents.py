"""Edge-case coverage for ``app/api/agents.py`` and the auth-related
dependencies in ``app/api/deps.py`` it uses.

``tests/test_smoke.py`` already walks the golden path end to end
(register -> list -> get -> update -> pause -> resume -> execute ->
retire, plus tool/task create+list). This file covers what that smoke
test does not: the router-registration-order regression this module's
own docstring documents, authentication edge cases, Pydantic
validation edge cases, not-found/conflict paths, and cross-tenant
isolation.

**A note on status codes.** This service's global exception handler
(``shared_core.exceptions.handlers.register_exception_handlers``)
converts every ``RequestValidationError`` -- a missing field, an
out-of-range value, an invalid enum member -- into a
``shared_core.exceptions.validation.ValidationError``, whose own
``status_code`` class attribute is ``400``, not FastAPI's stock
``422``. So a schema-validation failure at the HTTP layer in this
codebase is genuinely a ``400``, asserted below as
``HTTP_BAD_REQUEST`` -- this is real, verified behaviour, not a
mistaken substitution for the usual FastAPI default.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.security import HTTPAuthorizationCredentials
from httpx import AsyncClient
from shared_core.exceptions.authentication import AuthenticationError
from shared_core.security.jwt import encode_token
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.deps import get_audit_service, get_caller_token, get_current_user_id, get_db_session
from app.repositories.governance import AgentAuditRepository
from app.services.reporting import AuditService
from tests.conftest import (
    HTTP_BAD_REQUEST,
    HTTP_CONFLICT,
    HTTP_CREATED,
    HTTP_NOT_FOUND,
    HTTP_OK,
    HTTP_UNAUTHORIZED,
    AuthHeadersFn,
)


def _agent_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "slug": f"agent-{uuid.uuid4().hex[:12]}",
        "name": "Test Agent",
        "agent_type": "executor",
    }
    payload.update(overrides)
    return payload


async def _register_agent(
    client: AsyncClient,
    headers: dict[str, str],
    organization_id: uuid.UUID,
    **overrides: Any,
) -> dict[str, Any]:
    response = await client.post(
        "/agents",
        params={"organization_id": str(organization_id)},
        json=_agent_payload(**overrides),
        headers=headers,
    )
    assert response.status_code == HTTP_CREATED, response.text
    return response.json()["data"]


# ---- router-registration-order regression ----------------------------------


class TestRouterRegistrationOrderRegression:
    """``app/api/agents.py``'s own docstring: every static-segment route
    must be registered before ``GET/PUT/DELETE /{agent_id}``, or the
    catch-all would hijack it and fail UUID parsing on the literal path
    segment (e.g. ``"tasks"``) before the real handler ever ran. A
    hijack would surface as this app's own validation-failure status
    (400, see this module's docstring) instead of 200 -- these tests
    assert the correct route won, not merely "some 2xx happened".
    """

    async def test_tasks_route_not_hijacked(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        response = await client.get(
            "/agents/tasks", params={"organization_id": str(organization_id)}
        )
        assert response.status_code == HTTP_OK, response.text
        body = response.json()
        assert body["success"] is True
        assert body["data"] == []

    async def test_tools_route_not_hijacked(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        response = await client.get(
            "/agents/tools", params={"organization_id": str(organization_id)}
        )
        assert response.status_code == HTTP_OK, response.text
        assert response.json()["data"] == []

    async def test_evaluations_route_not_hijacked(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        response = await client.get(
            "/agents/evaluations", params={"organization_id": str(organization_id)}
        )
        assert response.status_code == HTTP_OK, response.text
        assert response.json()["data"] == []

    async def test_benchmarks_route_not_hijacked(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        response = await client.get(
            "/agents/benchmarks", params={"organization_id": str(organization_id)}
        )
        assert response.status_code == HTTP_OK, response.text
        assert response.json()["data"] == []

    async def test_statistics_route_not_hijacked(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        response = await client.get(
            "/agents/statistics", params={"organization_id": str(organization_id)}
        )
        assert response.status_code == HTTP_OK, response.text
        assert response.json()["data"] is None

    async def test_reports_route_not_hijacked(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        response = await client.get(
            "/agents/reports", params={"organization_id": str(organization_id)}
        )
        assert response.status_code == HTTP_OK, response.text
        assert response.json()["data"] == []

    async def test_agent_id_catchall_still_matches_real_uuids(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        agent = await _register_agent(client, headers, organization_id)
        response = await client.get(
            f"/agents/{agent['id']}", params={"organization_id": str(organization_id)}
        )
        assert response.status_code == HTTP_OK
        assert response.json()["data"]["id"] == agent["id"]


# ---- authentication edge cases ----------------------------------------------


class TestAuthenticationEdgeCases:
    async def test_register_agent_without_auth_header_401(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        response = await client.post(
            "/agents", params={"organization_id": str(organization_id)}, json=_agent_payload()
        )
        assert response.status_code == HTTP_UNAUTHORIZED
        assert response.json()["success"] is False

    async def test_register_agent_with_garbage_jwt_401(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        headers = {"Authorization": "Bearer this-is-not-a-real-jwt"}
        response = await client.post(
            "/agents",
            params={"organization_id": str(organization_id)},
            json=_agent_payload(),
            headers=headers,
        )
        assert response.status_code == HTTP_UNAUTHORIZED

    async def test_register_agent_with_expired_jwt_401(
        self,
        client: AsyncClient,
        organization_id: uuid.UUID,
        jwt_keypair: tuple[str, str],
    ) -> None:
        private_key, _public_key = jwt_keypair
        expired_token = encode_token(
            {"sub": str(uuid.uuid4()), "role": "super_admin", "scopes": []},
            private_key=private_key,
            ttl_seconds=-3_600,
        )
        headers = {"Authorization": f"Bearer {expired_token}"}
        response = await client.post(
            "/agents",
            params={"organization_id": str(organization_id)},
            json=_agent_payload(),
            headers=headers,
        )
        assert response.status_code == HTTP_UNAUTHORIZED

    async def test_create_task_without_auth_header_401(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        response = await client.post(
            "/agents/tasks",
            params={"organization_id": str(organization_id)},
            json={"task_type": "unauthorized-task"},
        )
        assert response.status_code == HTTP_UNAUTHORIZED

    async def test_retire_agent_without_auth_header_401(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        agent = await _register_agent(client, auth_headers(uuid.uuid4()), organization_id)
        response = await client.delete(
            f"/agents/{agent['id']}", params={"organization_id": str(organization_id)}
        )
        assert response.status_code == HTTP_UNAUTHORIZED

    async def test_list_agents_does_not_require_auth(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        response = await client.get("/agents", params={"organization_id": str(organization_id)})
        assert response.status_code == HTTP_OK

    async def test_get_agent_does_not_require_auth(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        agent = await _register_agent(client, auth_headers(uuid.uuid4()), organization_id)
        response = await client.get(
            f"/agents/{agent['id']}", params={"organization_id": str(organization_id)}
        )
        assert response.status_code == HTTP_OK

    async def test_update_agent_does_not_require_auth(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        agent = await _register_agent(client, auth_headers(uuid.uuid4()), organization_id)
        response = await client.put(
            f"/agents/{agent['id']}",
            params={"organization_id": str(organization_id)},
            json={"description": "no auth needed"},
        )
        assert response.status_code == HTTP_OK

    async def test_pause_and_resume_do_not_require_auth(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        agent = await _register_agent(client, auth_headers(uuid.uuid4()), organization_id)
        params = {"organization_id": str(organization_id)}
        paused = await client.post(f"/agents/{agent['id']}/pause", params=params)
        assert paused.status_code == HTTP_OK
        resumed = await client.post(f"/agents/{agent['id']}/resume", params=params)
        assert resumed.status_code == HTTP_OK

    async def test_register_tool_does_not_require_auth(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        response = await client.post(
            "/agents/tools",
            params={"organization_id": str(organization_id)},
            json={"tool_key": "no.auth.tool", "name": "No Auth Tool", "tool_kind": "rest"},
        )
        assert response.status_code == HTTP_CREATED


class TestDependencyFunctionsDirectly:
    """Direct coverage of ``get_caller_token``/``get_current_user_id``'s
    own branches, per this suite's mandate to confirm
    ``get_caller_token`` returns ``""`` for no credentials."""

    async def test_get_caller_token_returns_empty_string_without_credentials(self) -> None:
        assert await get_caller_token(None) == ""

    async def test_get_caller_token_forwards_raw_bearer_value(self) -> None:
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="raw-token-value")
        assert await get_caller_token(credentials) == "raw-token-value"

    async def test_get_current_user_id_raises_without_credentials(self) -> None:
        with pytest.raises(AuthenticationError):
            await get_current_user_id(None, None)  # type: ignore[arg-type]


class TestGetDbSessionDirectly:
    """Direct coverage of ``get_db_session``'s own generator body.

    The ``app`` fixture overrides this exact dependency for every
    HTTP-level test in this suite (see ``tests/conftest.py``'s own
    docstring), so its real body never runs through a request. Drive it
    directly against a real SAVEPOINT-isolated session factory instead.
    """

    async def test_yields_a_working_session_and_commits_on_success(
        self, db_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        class _FakeState:
            def __init__(self) -> None:
                self.db_session_factory = db_session_factory

        class _FakeApp:
            def __init__(self) -> None:
                self.state = _FakeState()

        class _FakeRequest:
            def __init__(self) -> None:
                self.app = _FakeApp()

        generator = get_db_session(_FakeRequest())  # type: ignore[arg-type]
        session = await generator.__anext__()
        assert isinstance(session, AsyncSession)
        result = await session.execute(text("SELECT 1"))
        assert result.scalar_one() == 1
        with pytest.raises(StopAsyncIteration):
            await generator.__anext__()


class TestGetAuditServiceDirectly:
    """``get_audit_service`` builds a service no ``app/api/agents.py``
    route currently depends on -- covered directly rather than via HTTP."""

    async def test_builds_service_around_audit_repository(self, db_session: AsyncSession) -> None:
        service = get_audit_service(db_session)
        assert isinstance(service, AuditService)
        assert isinstance(service._audits, AgentAuditRepository)


# ---- request-body / query-param validation edge cases -----------------------


class TestAgentRegistrationValidation:
    async def test_missing_required_field_rejected(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        response = await client.post(
            "/agents",
            params={"organization_id": str(organization_id)},
            json={"name": "No Slug", "agent_type": "executor"},
            headers=auth_headers(uuid.uuid4()),
        )
        assert response.status_code == HTTP_BAD_REQUEST
        body = response.json()
        assert body["success"] is False
        assert body["error"]["code"] == "AIIOS-VAL-0001"

    async def test_empty_slug_rejected(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        response = await client.post(
            "/agents",
            params={"organization_id": str(organization_id)},
            json=_agent_payload(slug=""),
            headers=auth_headers(uuid.uuid4()),
        )
        assert response.status_code == HTTP_BAD_REQUEST

    async def test_slug_too_long_rejected(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        response = await client.post(
            "/agents",
            params={"organization_id": str(organization_id)},
            json=_agent_payload(slug="x" * 65),
            headers=auth_headers(uuid.uuid4()),
        )
        assert response.status_code == HTTP_BAD_REQUEST

    async def test_empty_name_rejected(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        response = await client.post(
            "/agents",
            params={"organization_id": str(organization_id)},
            json=_agent_payload(name=""),
            headers=auth_headers(uuid.uuid4()),
        )
        assert response.status_code == HTTP_BAD_REQUEST

    async def test_invalid_agent_type_rejected(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        response = await client.post(
            "/agents",
            params={"organization_id": str(organization_id)},
            json=_agent_payload(agent_type="not-a-real-type"),
            headers=auth_headers(uuid.uuid4()),
        )
        assert response.status_code == HTTP_BAD_REQUEST

    async def test_missing_organization_id_query_param_rejected(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        response = await client.post(
            "/agents", json=_agent_payload(), headers=auth_headers(uuid.uuid4())
        )
        assert response.status_code == HTTP_BAD_REQUEST

    async def test_profile_temperature_out_of_range_rejected(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        response = await client.post(
            "/agents",
            params={"organization_id": str(organization_id)},
            json=_agent_payload(profile={"temperature": 2.5}),
            headers=auth_headers(uuid.uuid4()),
        )
        assert response.status_code == HTTP_BAD_REQUEST

    async def test_profile_max_tokens_out_of_range_rejected(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        response = await client.post(
            "/agents",
            params={"organization_id": str(organization_id)},
            json=_agent_payload(profile={"max_tokens": 0}),
            headers=auth_headers(uuid.uuid4()),
        )
        assert response.status_code == HTTP_BAD_REQUEST

        response_too_high = await client.post(
            "/agents",
            params={"organization_id": str(organization_id)},
            json=_agent_payload(profile={"max_tokens": 200_001}),
            headers=auth_headers(uuid.uuid4()),
        )
        assert response_too_high.status_code == HTTP_BAD_REQUEST


class TestAgentUpdateValidation:
    async def test_empty_name_rejected_when_provided(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        agent = await _register_agent(client, auth_headers(uuid.uuid4()), organization_id)
        response = await client.put(
            f"/agents/{agent['id']}",
            params={"organization_id": str(organization_id)},
            json={"name": ""},
        )
        assert response.status_code == HTTP_BAD_REQUEST


class TestAgentExecuteValidation:
    async def test_empty_request_rejected(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        agent = await _register_agent(client, auth_headers(uuid.uuid4()), organization_id)
        response = await client.post(
            f"/agents/{agent['id']}/execute",
            params={"organization_id": str(organization_id)},
            json={"request": ""},
        )
        assert response.status_code == HTTP_BAD_REQUEST

    async def test_invalid_session_id_rejected(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        agent = await _register_agent(client, auth_headers(uuid.uuid4()), organization_id)
        response = await client.post(
            f"/agents/{agent['id']}/execute",
            params={"organization_id": str(organization_id)},
            json={"request": "hello", "session_id": "not-a-uuid"},
        )
        assert response.status_code == HTTP_BAD_REQUEST


class TestTaskValidation:
    async def test_missing_task_type_rejected(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        response = await client.post(
            "/agents/tasks",
            params={"organization_id": str(organization_id)},
            json={},
            headers=auth_headers(uuid.uuid4()),
        )
        assert response.status_code == HTTP_BAD_REQUEST

    async def test_empty_task_type_rejected(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        response = await client.post(
            "/agents/tasks",
            params={"organization_id": str(organization_id)},
            json={"task_type": ""},
            headers=auth_headers(uuid.uuid4()),
        )
        assert response.status_code == HTTP_BAD_REQUEST

    async def test_max_retries_out_of_range_rejected(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        response = await client.post(
            "/agents/tasks",
            params={"organization_id": str(organization_id)},
            json={"task_type": "t", "max_retries": 21},
            headers=auth_headers(uuid.uuid4()),
        )
        assert response.status_code == HTTP_BAD_REQUEST

    async def test_timeout_seconds_must_be_positive(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        response = await client.post(
            "/agents/tasks",
            params={"organization_id": str(organization_id)},
            json={"task_type": "t", "timeout_seconds": 0},
            headers=auth_headers(uuid.uuid4()),
        )
        assert response.status_code == HTTP_BAD_REQUEST

    async def test_invalid_priority_rejected(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        response = await client.post(
            "/agents/tasks",
            params={"organization_id": str(organization_id)},
            json={"task_type": "t", "priority": "urgent"},
            headers=auth_headers(uuid.uuid4()),
        )
        assert response.status_code == HTTP_BAD_REQUEST

    async def test_limit_out_of_range_rejected(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        too_small = await client.get(
            "/agents/tasks", params={"organization_id": str(organization_id), "limit": 0}
        )
        assert too_small.status_code == HTTP_BAD_REQUEST
        too_large = await client.get(
            "/agents/tasks", params={"organization_id": str(organization_id), "limit": 1_001}
        )
        assert too_large.status_code == HTTP_BAD_REQUEST

    async def test_negative_offset_rejected(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        response = await client.get(
            "/agents/tasks", params={"organization_id": str(organization_id), "offset": -1}
        )
        assert response.status_code == HTTP_BAD_REQUEST

    async def test_invalid_status_filter_rejected(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        response = await client.get(
            "/agents/tasks",
            params={"organization_id": str(organization_id), "status": "not-a-real-status"},
        )
        assert response.status_code == HTTP_BAD_REQUEST


class TestToolValidation:
    async def test_missing_tool_key_rejected(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        response = await client.post(
            "/agents/tools",
            params={"organization_id": str(organization_id)},
            json={"name": "No Key", "tool_kind": "rest"},
        )
        assert response.status_code == HTTP_BAD_REQUEST

    async def test_empty_tool_key_rejected(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        response = await client.post(
            "/agents/tools",
            params={"organization_id": str(organization_id)},
            json={"tool_key": "", "name": "Empty Key", "tool_kind": "rest"},
        )
        assert response.status_code == HTTP_BAD_REQUEST

    async def test_invalid_tool_kind_rejected(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        response = await client.post(
            "/agents/tools",
            params={"organization_id": str(organization_id)},
            json={"tool_key": "bad.kind", "name": "Bad Kind", "tool_kind": "not-a-real-kind"},
        )
        assert response.status_code == HTTP_BAD_REQUEST

    async def test_limit_out_of_range_rejected(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        response = await client.get(
            "/agents/tools", params={"organization_id": str(organization_id), "limit": 1_001}
        )
        assert response.status_code == HTTP_BAD_REQUEST


class TestListAgentsValidation:
    async def test_invalid_agent_type_filter_rejected(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        response = await client.get(
            "/agents",
            params={"organization_id": str(organization_id), "agent_type": "not-a-real-type"},
        )
        assert response.status_code == HTTP_BAD_REQUEST

    async def test_invalid_organization_id_rejected(self, client: AsyncClient) -> None:
        response = await client.get("/agents", params={"organization_id": "not-a-uuid"})
        assert response.status_code == HTTP_BAD_REQUEST


class TestReportsValidation:
    async def test_invalid_kind_filter_rejected(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        response = await client.get(
            "/agents/reports",
            params={"organization_id": str(organization_id), "kind": "not-a-real-kind"},
        )
        assert response.status_code == HTTP_BAD_REQUEST

    async def test_valid_kind_filter_returns_empty_list(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        response = await client.get(
            "/agents/reports", params={"organization_id": str(organization_id), "kind": "usage"}
        )
        assert response.status_code == HTTP_OK
        assert response.json()["data"] == []


# ---- not-found / conflict paths ---------------------------------------------


class TestNotFoundPaths:
    async def test_get_unknown_agent_404(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        response = await client.get(
            f"/agents/{uuid.uuid4()}", params={"organization_id": str(organization_id)}
        )
        assert response.status_code == HTTP_NOT_FOUND
        body = response.json()
        assert body["success"] is False
        assert body["error"]["code"] == "AIIOS-NF-0001"

    async def test_update_unknown_agent_404(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        response = await client.put(
            f"/agents/{uuid.uuid4()}",
            params={"organization_id": str(organization_id)},
            json={"description": "does not matter"},
        )
        assert response.status_code == HTTP_NOT_FOUND

    async def test_delete_unknown_agent_404(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        response = await client.delete(
            f"/agents/{uuid.uuid4()}",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
        )
        assert response.status_code == HTTP_NOT_FOUND

    async def test_pause_unknown_agent_404(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        response = await client.post(
            f"/agents/{uuid.uuid4()}/pause", params={"organization_id": str(organization_id)}
        )
        assert response.status_code == HTTP_NOT_FOUND

    async def test_resume_unknown_agent_404(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        response = await client.post(
            f"/agents/{uuid.uuid4()}/resume", params={"organization_id": str(organization_id)}
        )
        assert response.status_code == HTTP_NOT_FOUND

    async def test_execute_unknown_agent_404(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        response = await client.post(
            f"/agents/{uuid.uuid4()}/execute",
            params={"organization_id": str(organization_id)},
            json={"request": "hello"},
        )
        assert response.status_code == HTTP_NOT_FOUND


class TestConflictPaths:
    async def test_duplicate_slug_in_same_org_conflicts(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        await _register_agent(client, headers, organization_id, slug="dup-slug")
        response = await client.post(
            "/agents",
            params={"organization_id": str(organization_id)},
            json=_agent_payload(slug="dup-slug"),
            headers=headers,
        )
        assert response.status_code == HTTP_CONFLICT
        body = response.json()
        assert body["success"] is False
        assert body["error"]["code"] == "AIIOS-CONFLICT-0001"

    async def test_same_slug_in_different_orgs_does_not_conflict(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        other_org = uuid.uuid4()
        headers = auth_headers(uuid.uuid4())
        await _register_agent(client, headers, organization_id, slug="shared-slug")
        response = await client.post(
            "/agents",
            params={"organization_id": str(other_org)},
            json=_agent_payload(slug="shared-slug"),
            headers=headers,
        )
        assert response.status_code == HTTP_CREATED

    async def test_pause_already_paused_agent_conflicts(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        agent = await _register_agent(client, auth_headers(uuid.uuid4()), organization_id)
        params = {"organization_id": str(organization_id)}
        first = await client.post(f"/agents/{agent['id']}/pause", params=params)
        assert first.status_code == HTTP_OK
        second = await client.post(f"/agents/{agent['id']}/pause", params=params)
        assert second.status_code == HTTP_CONFLICT
        assert second.json()["error"]["code"] == "AIIOS-CONFLICT-0001"

    async def test_resume_non_paused_agent_conflicts(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        agent = await _register_agent(client, auth_headers(uuid.uuid4()), organization_id)
        response = await client.post(
            f"/agents/{agent['id']}/resume", params={"organization_id": str(organization_id)}
        )
        assert response.status_code == HTTP_CONFLICT

    async def test_duplicate_tool_key_in_same_org_conflicts(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        params = {"organization_id": str(organization_id)}
        body = {"tool_key": "dup.tool.key", "name": "Dup Tool", "tool_kind": "rest"}
        first = await client.post("/agents/tools", params=params, json=body)
        assert first.status_code == HTTP_CREATED
        second = await client.post("/agents/tools", params=params, json=body)
        assert second.status_code == HTTP_CONFLICT
        assert second.json()["error"]["code"] == "AIIOS-CONFLICT-0001"


# ---- cross-tenant isolation --------------------------------------------------


class TestTenantIsolation:
    async def test_get_agent_from_wrong_org_404(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        other_org = uuid.uuid4()
        agent = await _register_agent(client, auth_headers(uuid.uuid4()), organization_id)
        response = await client.get(
            f"/agents/{agent['id']}", params={"organization_id": str(other_org)}
        )
        assert response.status_code == HTTP_NOT_FOUND

    async def test_update_agent_from_wrong_org_404(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        other_org = uuid.uuid4()
        agent = await _register_agent(client, auth_headers(uuid.uuid4()), organization_id)
        response = await client.put(
            f"/agents/{agent['id']}",
            params={"organization_id": str(other_org)},
            json={"description": "should not apply"},
        )
        assert response.status_code == HTTP_NOT_FOUND

    async def test_delete_agent_from_wrong_org_404(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        other_org = uuid.uuid4()
        headers = auth_headers(uuid.uuid4())
        agent = await _register_agent(client, headers, organization_id)
        response = await client.delete(
            f"/agents/{agent['id']}", params={"organization_id": str(other_org)}, headers=headers
        )
        assert response.status_code == HTTP_NOT_FOUND

    async def test_pause_agent_from_wrong_org_404(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        other_org = uuid.uuid4()
        agent = await _register_agent(client, auth_headers(uuid.uuid4()), organization_id)
        response = await client.post(
            f"/agents/{agent['id']}/pause", params={"organization_id": str(other_org)}
        )
        assert response.status_code == HTTP_NOT_FOUND

    async def test_execute_agent_from_wrong_org_404(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        other_org = uuid.uuid4()
        agent = await _register_agent(client, auth_headers(uuid.uuid4()), organization_id)
        response = await client.post(
            f"/agents/{agent['id']}/execute",
            params={"organization_id": str(other_org)},
            json={"request": "hello"},
        )
        assert response.status_code == HTTP_NOT_FOUND

    async def test_list_agents_scoped_to_own_org_only(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        other_org = uuid.uuid4()
        await _register_agent(client, auth_headers(uuid.uuid4()), organization_id)
        response = await client.get("/agents", params={"organization_id": str(other_org)})
        assert response.status_code == HTTP_OK
        assert response.json()["data"] == []

    async def test_list_tasks_scoped_to_own_org_only(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        other_org = uuid.uuid4()
        headers = auth_headers(uuid.uuid4())
        await client.post(
            "/agents/tasks",
            params={"organization_id": str(organization_id)},
            json={"task_type": "isolated-task"},
            headers=headers,
        )
        response = await client.get("/agents/tasks", params={"organization_id": str(other_org)})
        assert response.status_code == HTTP_OK
        assert response.json()["data"] == []


# ---- listing / filtering behaviour -------------------------------------------


class TestListingAndFiltering:
    async def test_list_agents_filtered_by_type(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        await _register_agent(client, headers, organization_id, agent_type="planner")
        await _register_agent(client, headers, organization_id, agent_type="executor")

        response = await client.get(
            "/agents", params={"organization_id": str(organization_id), "agent_type": "planner"}
        )
        assert response.status_code == HTTP_OK
        data = response.json()["data"]
        assert len(data) == 1
        assert data[0]["agent_type"] == "planner"

    async def test_list_tasks_filtered_by_status(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        params = {"organization_id": str(organization_id)}
        created = await client.post(
            "/agents/tasks", params=params, json={"task_type": "filter-me"}, headers=headers
        )
        assert created.status_code == HTTP_CREATED

        pending = await client.get("/agents/tasks", params={**params, "status": "pending"})
        assert pending.status_code == HTTP_OK
        assert len(pending.json()["data"]) == 1

        running = await client.get("/agents/tasks", params={**params, "status": "running"})
        assert running.status_code == HTTP_OK
        assert running.json()["data"] == []

    async def test_statistics_returns_null_when_none_computed(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        response = await client.get(
            "/agents/statistics", params={"organization_id": str(organization_id)}
        )
        assert response.status_code == HTTP_OK
        assert response.json()["data"] is None


# ---- partial update semantics ------------------------------------------------


class TestAgentUpdateSemantics:
    async def test_update_only_changes_provided_fields(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        agent = await _register_agent(
            client,
            auth_headers(uuid.uuid4()),
            organization_id,
            name="Original Name",
            owner_id="owner-1",
        )
        response = await client.put(
            f"/agents/{agent['id']}",
            params={"organization_id": str(organization_id)},
            json={"description": "only description changed"},
        )
        assert response.status_code == HTTP_OK
        updated = response.json()["data"]
        assert updated["description"] == "only description changed"
        assert updated["name"] == "Original Name"
        assert updated["owner_id"] == "owner-1"

    async def test_update_tags(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        agent = await _register_agent(
            client, auth_headers(uuid.uuid4()), organization_id, tags=["a"]
        )
        response = await client.put(
            f"/agents/{agent['id']}",
            params={"organization_id": str(organization_id)},
            json={"tags": ["b", "c"]},
        )
        assert response.status_code == HTTP_OK
        assert response.json()["data"]["tags"] == ["b", "c"]


# ---- response shape -----------------------------------------------------------


class TestAgentResponseShape:
    async def test_get_agent_response_contains_all_documented_fields(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
    ) -> None:
        agent = await _register_agent(client, auth_headers(uuid.uuid4()), organization_id)
        response = await client.get(
            f"/agents/{agent['id']}", params={"organization_id": str(organization_id)}
        )
        assert response.status_code == HTTP_OK
        data = response.json()["data"]
        expected_keys = {
            "id",
            "organization_id",
            "slug",
            "name",
            "description",
            "agent_type",
            "status",
            "current_version_number",
            "tags",
            "owner_id",
            "consecutive_failures",
            "last_executed_at",
            "created_at",
        }
        assert set(data.keys()) == expected_keys
        assert data["status"] == "active"
        assert data["consecutive_failures"] == 0
