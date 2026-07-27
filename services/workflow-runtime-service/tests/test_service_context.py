"""Tests for :class:`app.services.context.WorkflowContextEntryService`."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workflow_instance import WorkflowInstance
from app.repositories.workflow_context import WorkflowContextEntryRepository
from app.services.context import WorkflowContextEntryService
from tests.conftest import build_version_service, make_definition, make_instance


def _build_service(db_session: AsyncSession) -> WorkflowContextEntryService:
    return WorkflowContextEntryService(WorkflowContextEntryRepository(db_session))


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


class TestWorkflowContextEntryService:
    async def test_record(self, db_session: AsyncSession) -> None:
        instance = await _linear_instance(db_session)
        service = _build_service(db_session)
        entry = await service.record(
            organization_id=instance.organization_id,
            instance_id=instance.id,
            key="connector_context",
            value={"host": "10.0.0.1"},
        )
        assert entry.key == "connector_context"
        assert entry.value == {"host": "10.0.0.1"}

    async def test_list_for_instance(self, db_session: AsyncSession) -> None:
        instance = await _linear_instance(db_session)
        service = _build_service(db_session)
        await service.record(
            organization_id=instance.organization_id,
            instance_id=instance.id,
            key="ai_context",
            value={"model": "gpt"},
        )
        entries = await service.list_for_instance(instance.id)
        assert len(entries) == 1
