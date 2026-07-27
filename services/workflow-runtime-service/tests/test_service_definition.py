"""Tests for :class:`app.services.definition.WorkflowDefinitionService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import build_definition_service, linear_nodes_and_edges


class TestWorkflowDefinitionService:
    async def test_create_creates_definition_and_first_version(
        self, db_session: AsyncSession
    ) -> None:
        nodes, edges = linear_nodes_and_edges()
        service = build_definition_service(db_session)
        definition = await service.create(
            organization_id=uuid.uuid4(),
            project_id=None,
            workflow_key="deploy-app",
            name="Deploy App",
            description="Deploys the app.",
            owner=None,
            tags=[],
            default_variables={},
            nodes=nodes,
            edges=edges,
        )
        assert definition.workflow_key == "deploy-app"
        assert definition.current_version_number == "1.0.0"

    async def test_create_duplicate_workflow_key_raises_conflict(
        self, db_session: AsyncSession
    ) -> None:
        nodes, edges = linear_nodes_and_edges()
        org_id = uuid.uuid4()
        service = build_definition_service(db_session)
        await service.create(
            organization_id=org_id,
            project_id=None,
            workflow_key="deploy-app",
            name="Deploy App",
            description=None,
            owner=None,
            tags=[],
            default_variables={},
            nodes=nodes,
            edges=edges,
        )
        with pytest.raises(ConflictError):
            await service.create(
                organization_id=org_id,
                project_id=None,
                workflow_key="deploy-app",
                name="Deploy App Again",
                description=None,
                owner=None,
                tags=[],
                default_variables={},
                nodes=nodes,
                edges=edges,
            )

    async def test_get_by_id_missing_raises(self, db_session: AsyncSession) -> None:
        service = build_definition_service(db_session)
        with pytest.raises(NotFoundError):
            await service.get_by_id(uuid.uuid4())

    async def test_list_for_org(self, db_session: AsyncSession) -> None:
        nodes, edges = linear_nodes_and_edges()
        org_id = uuid.uuid4()
        service = build_definition_service(db_session)
        await service.create(
            organization_id=org_id,
            project_id=None,
            workflow_key="wf-1",
            name="WF 1",
            description=None,
            owner=None,
            tags=[],
            default_variables={},
            nodes=nodes,
            edges=edges,
        )
        definitions = await service.list_for_org(org_id)
        assert len(definitions) == 1

    async def test_update_bumps_version(self, db_session: AsyncSession) -> None:
        nodes, edges = linear_nodes_and_edges()
        service = build_definition_service(db_session)
        definition = await service.create(
            organization_id=uuid.uuid4(),
            project_id=None,
            workflow_key="wf-1",
            name="WF 1",
            description=None,
            owner=None,
            tags=[],
            default_variables={},
            nodes=nodes,
            edges=edges,
        )
        updated = await service.update(
            definition.id,
            name="WF 1 renamed",
            description="Updated.",
            owner="team-a",
            tags=["prod"],
            default_variables={"region": "us-east-1"},
            nodes=nodes,
            edges=edges,
        )
        assert updated.name == "WF 1 renamed"
        assert updated.current_version_number == "1.0.1"

    async def test_delete_soft_deletes(self, db_session: AsyncSession) -> None:
        nodes, edges = linear_nodes_and_edges()
        service = build_definition_service(db_session)
        definition = await service.create(
            organization_id=uuid.uuid4(),
            project_id=None,
            workflow_key="wf-1",
            name="WF 1",
            description=None,
            owner=None,
            tags=[],
            default_variables={},
            nodes=nodes,
            edges=edges,
        )
        await service.delete(definition.id)
        with pytest.raises(NotFoundError):
            await service.get_by_id(definition.id)
