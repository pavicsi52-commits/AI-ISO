"""Tests for :class:`app.services.variable.WorkflowVariableService`."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import WorkflowVariableScope
from app.models.workflow_instance import WorkflowInstance
from app.repositories.workflow_variable import WorkflowVariableRepository
from app.services.variable import WorkflowVariableService
from tests.conftest import build_version_service, make_definition, make_instance


def _build_service(db_session: AsyncSession) -> WorkflowVariableService:
    return WorkflowVariableService(WorkflowVariableRepository(db_session))


async def _linear_instance(db_session: AsyncSession) -> WorkflowInstance:
    definition = await make_definition(db_session)
    version = await build_version_service(db_session).create_version(
        definition,
        nodes=[
            {"node_id": "start", "node_type": "start", "name": "start"},
            {"node_id": "end", "node_type": "end", "name": "end"},
        ],
        edges=[{"from_node_id": "start", "to_node_id": "end"}],
        current_version_number=None,
    )
    return await make_instance(db_session, definition, version)


class TestWorkflowVariableService:
    async def test_record_for_definition(self, db_session: AsyncSession) -> None:
        instance = await _linear_instance(db_session)
        service = _build_service(db_session)
        variable = await service.record_for_definition(
            organization_id=instance.organization_id,
            definition_id=instance.definition_id,
            name="region",
            value="us-east-1",
        )
        assert variable.instance_id is None
        assert variable.scope == WorkflowVariableScope.WORKFLOW

    async def test_record_for_instance(self, db_session: AsyncSession) -> None:
        instance = await _linear_instance(db_session)
        service = _build_service(db_session)
        variable = await service.record_for_instance(
            organization_id=instance.organization_id,
            definition_id=instance.definition_id,
            instance_id=instance.id,
            name="computed_value",
            value=42,
            is_secret=True,
        )
        assert variable.instance_id == instance.id
        assert variable.scope == WorkflowVariableScope.RUNTIME
        assert variable.is_secret is True

    async def test_list_for_definition_excludes_instance_scoped(
        self, db_session: AsyncSession
    ) -> None:
        instance = await _linear_instance(db_session)
        service = _build_service(db_session)
        await service.record_for_definition(
            organization_id=instance.organization_id,
            definition_id=instance.definition_id,
            name="default_region",
            value="us-east-1",
        )
        await service.record_for_instance(
            organization_id=instance.organization_id,
            definition_id=instance.definition_id,
            instance_id=instance.id,
            name="runtime_value",
            value=1,
        )
        definition_variables = await service.list_for_definition(instance.definition_id)
        assert len(definition_variables) == 1
        assert definition_variables[0].name == "default_region"

    async def test_list_for_instance(self, db_session: AsyncSession) -> None:
        instance = await _linear_instance(db_session)
        service = _build_service(db_session)
        await service.record_for_instance(
            organization_id=instance.organization_id,
            definition_id=instance.definition_id,
            instance_id=instance.id,
            name="runtime_value",
            value=1,
        )
        instance_variables = await service.list_for_instance(instance.id)
        assert len(instance_variables) == 1
