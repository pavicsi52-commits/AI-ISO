"""Tests for the ``/workflow-instances`` router, including its
``logs``/``checkpoints``/``approvals`` actions.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from shared_core.workflow import NodeType
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import NodeExecutionStatus
from app.models.workflow_execution_step import WorkflowExecutionStep
from app.repositories.workflow_approval import WorkflowApprovalRepository
from app.repositories.workflow_execution_step import WorkflowExecutionStepRepository
from app.services.approval import WorkflowApprovalService
from tests.conftest import AuthHeadersFn


def _create_body(organization_id: uuid.UUID) -> dict[str, object]:
    return {
        "organization_id": str(organization_id),
        "workflow_key": "deploy-app",
        "name": "Deploy App",
        "nodes": [
            {"node_id": "start", "node_type": "start", "name": "start"},
            {"node_id": "end", "node_type": "end", "name": "end"},
        ],
        "edges": [{"from_node_id": "start", "to_node_id": "end"}],
    }


async def _create_and_execute(
    client: AsyncClient, headers: dict[str, str], org_id: uuid.UUID
) -> str:
    created = await client.post("/workflows", json=_create_body(org_id), headers=headers)
    workflow_id = created.json()["data"]["id"]
    executed = await client.post(
        f"/workflows/{workflow_id}/execute", json={"variables": {}}, headers=headers
    )
    return str(executed.json()["data"]["id"])


class TestInstancesApi:
    async def test_list_instances_filters_by_org(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        org_id = uuid.uuid4()
        await _create_and_execute(client, headers, org_id)

        response = await client.get(
            "/workflow-instances", params={"organization_id": str(org_id)}, headers=headers
        )
        assert response.status_code == 200
        assert len(response.json()["data"]) == 1

    async def test_get_instance(self, client: AsyncClient, auth_headers: AuthHeadersFn) -> None:
        headers = auth_headers(uuid.uuid4())
        instance_id = await _create_and_execute(client, headers, uuid.uuid4())

        response = await client.get(f"/workflow-instances/{instance_id}", headers=headers)
        assert response.status_code == 200
        assert response.json()["data"]["id"] == instance_id

    async def test_get_missing_instance_returns_404(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        response = await client.get(f"/workflow-instances/{uuid.uuid4()}", headers=headers)
        assert response.status_code == 404

    async def test_list_instance_logs_empty(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        instance_id = await _create_and_execute(client, headers, uuid.uuid4())

        response = await client.get(f"/workflow-instances/{instance_id}/logs", headers=headers)
        assert response.status_code == 200
        assert isinstance(response.json()["data"], list)

    async def test_list_instance_steps(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, db_session: AsyncSession
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        instance_id = await _create_and_execute(client, headers, uuid.uuid4())

        await WorkflowExecutionStepRepository(db_session).create(
            WorkflowExecutionStep(
                organization_id=uuid.uuid4(),
                instance_id=uuid.UUID(instance_id),
                node_id="task",
                node_type=NodeType.TASK,
                status=NodeExecutionStatus.COMPLETED,
                attempts=1,
            )
        )

        response = await client.get(f"/workflow-instances/{instance_id}/steps", headers=headers)
        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data) == 1
        assert data[0]["node_id"] == "task"
        assert data[0]["status"] == "completed"

    async def test_list_instance_checkpoints_empty(
        self, client: AsyncClient, auth_headers: AuthHeadersFn
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        instance_id = await _create_and_execute(client, headers, uuid.uuid4())

        response = await client.get(
            f"/workflow-instances/{instance_id}/checkpoints", headers=headers
        )
        assert response.status_code == 200
        assert isinstance(response.json()["data"], list)

    async def test_list_and_decide_instance_approval(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, db_session: AsyncSession
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        instance_id = await _create_and_execute(client, headers, uuid.uuid4())

        approval = await WorkflowApprovalService(WorkflowApprovalRepository(db_session)).request(
            organization_id=uuid.uuid4(),
            instance_id=uuid.UUID(instance_id),
            node_id="approval",
            node_type=NodeType.APPROVAL,
            approvers=["alice"],
        )

        list_response = await client.get(
            f"/workflow-instances/{instance_id}/approvals", headers=headers
        )
        assert list_response.status_code == 200
        assert len(list_response.json()["data"]) == 1

        decide_response = await client.post(
            f"/workflow-instances/{instance_id}/approvals/{approval.id}/decide",
            json={"approver": "alice", "approve": True, "comments": "LGTM"},
            headers=headers,
        )
        assert decide_response.status_code == 200
        assert decide_response.json()["data"]["decision"] == "approved"

    async def test_endpoints_require_authentication(self, client: AsyncClient) -> None:
        response = await client.get(
            "/workflow-instances", params={"organization_id": str(uuid.uuid4())}
        )
        assert response.status_code == 401
