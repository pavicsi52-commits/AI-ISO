"""A minimal end-to-end smoke test, run once before dispatching the full test-writing pass.

Confirms the real app boots through its actual lifespan against real
PostgreSQL/Redis/RabbitMQ/Neo4j, and that the core agent lifecycle +
task + tool + execute path all work end to end through genuine HTTP
requests.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient

from tests.conftest import HTTP_CREATED, HTTP_OK, AuthHeadersFn


async def test_health_and_readiness(client: AsyncClient) -> None:
    health = await client.get("/health")
    assert health.status_code == HTTP_OK
    assert health.json()["data"]["status"] == "healthy"

    readiness = await client.get("/readiness")
    assert readiness.status_code == HTTP_OK
    assert readiness.json()["data"]["status"] in {"ready", "not_ready"}

    liveness = await client.get("/liveness")
    assert liveness.status_code == HTTP_OK
    assert liveness.json()["data"]["status"] == "alive"


async def test_full_agent_lifecycle_end_to_end(
    client: AsyncClient, auth_headers: AuthHeadersFn, organization_id: uuid.UUID
) -> None:
    headers = auth_headers(uuid.uuid4())
    params = {"organization_id": str(organization_id)}

    registered = await client.post(
        "/agents",
        params=params,
        json={
            "slug": "smoke-agent",
            "name": "Smoke Agent",
            "agent_type": "executor",
            "profile": {"reasoning_mode": "chain_of_thought"},
        },
        headers=headers,
    )
    assert registered.status_code == HTTP_CREATED, registered.text
    agent = registered.json()["data"]
    agent_id = agent["id"]
    assert agent["status"] == "active"

    listed = await client.get("/agents", params=params)
    assert listed.status_code == HTTP_OK
    assert any(row["id"] == agent_id for row in listed.json()["data"])

    fetched = await client.get(f"/agents/{agent_id}", params=params)
    assert fetched.status_code == HTTP_OK
    assert fetched.json()["data"]["slug"] == "smoke-agent"

    updated = await client.put(
        f"/agents/{agent_id}", params=params, json={"description": "Updated by smoke test."}
    )
    assert updated.status_code == HTTP_OK, updated.text
    assert updated.json()["data"]["description"] == "Updated by smoke test."

    tool_registered = await client.post(
        "/agents/tools",
        params=params,
        json={
            "tool_key": "smoke.echo",
            "name": "Smoke Echo",
            "tool_kind": "rest",
            "parameters_schema": {"type": "object", "properties": {"url": {"type": "string"}}},
        },
    )
    assert tool_registered.status_code == HTTP_CREATED, tool_registered.text

    tools_listed = await client.get("/agents/tools", params=params)
    assert tools_listed.status_code == HTTP_OK
    assert len(tools_listed.json()["data"]) == 1

    task_created = await client.post(
        "/agents/tasks",
        params=params,
        json={"task_type": "smoke-task", "payload": {"note": "hello"}, "agent_id": agent_id},
        headers=headers,
    )
    assert task_created.status_code == HTTP_CREATED, task_created.text
    assert task_created.json()["data"]["status"] == "pending"

    tasks_listed = await client.get("/agents/tasks", params=params)
    assert tasks_listed.status_code == HTTP_OK
    assert len(tasks_listed.json()["data"]) == 1

    paused = await client.post(f"/agents/{agent_id}/pause", params=params)
    assert paused.status_code == HTTP_OK, paused.text
    assert paused.json()["data"]["status"] == "paused"

    resumed = await client.post(f"/agents/{agent_id}/resume", params=params)
    assert resumed.status_code == HTTP_OK, resumed.text
    assert resumed.json()["data"]["status"] == "active"

    # No local model backend is guaranteed to be running in every
    # environment this suite executes in -- a real, well-formed
    # FAILED execution is as valid a smoke-test outcome as COMPLETED.
    # See tests/conftest.py's own module docstring.
    executed = await client.post(
        f"/agents/{agent_id}/execute",
        params=params,
        json={"request": "Reply with a brief acknowledgement."},
        headers=headers,
    )
    assert executed.status_code == HTTP_CREATED, executed.text
    execution = executed.json()["data"]
    assert execution["status"] in {"completed", "failed"}

    statistics = await client.get("/agents/statistics", params=params)
    assert statistics.status_code == HTTP_OK

    reports_listed = await client.get("/agents/reports", params=params)
    assert reports_listed.status_code == HTTP_OK
    assert reports_listed.json()["data"] == []

    retired = await client.delete(f"/agents/{agent_id}", params=params, headers=headers)
    assert retired.status_code == HTTP_OK, retired.text
    assert retired.json()["data"]["status"] == "retired"
