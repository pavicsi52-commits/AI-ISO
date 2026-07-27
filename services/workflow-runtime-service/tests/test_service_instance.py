"""Tests for :class:`app.services.instance.WorkflowInstanceService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import WorkflowInstanceStatus, WorkflowTriggerType
from app.models.workflow_definition import WorkflowDefinition
from app.models.workflow_version import WorkflowVersion
from tests.conftest import build_instance_service, build_version_service, make_definition


async def _definition_and_version(
    db_session: AsyncSession,
) -> tuple[WorkflowDefinition, WorkflowVersion]:
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
    return definition, version


class TestWorkflowInstanceService:
    async def test_create_sets_queued_status(self, db_session: AsyncSession) -> None:
        definition, version = await _definition_and_version(db_session)
        service = build_instance_service(db_session)
        instance = await service.create(
            organization_id=definition.organization_id,
            project_id=None,
            definition_id=definition.id,
            version_id=version.id,
            trigger_type=WorkflowTriggerType.MANUAL,
            triggered_by=uuid.uuid4(),
        )
        assert instance.status == WorkflowInstanceStatus.QUEUED

    async def test_get_by_id_missing_raises(self, db_session: AsyncSession) -> None:
        service = build_instance_service(db_session)
        with pytest.raises(NotFoundError):
            await service.get_by_id(uuid.uuid4())

    async def test_list_for_org_filters_by_status(self, db_session: AsyncSession) -> None:
        definition, version = await _definition_and_version(db_session)
        service = build_instance_service(db_session)
        await service.create(
            organization_id=definition.organization_id,
            project_id=None,
            definition_id=definition.id,
            version_id=version.id,
            trigger_type=WorkflowTriggerType.MANUAL,
            triggered_by=None,
        )
        queued = await service.list_for_org(
            definition.organization_id, status=WorkflowInstanceStatus.QUEUED
        )
        assert len(queued) == 1
        completed = await service.list_for_org(
            definition.organization_id, status=WorkflowInstanceStatus.COMPLETED
        )
        assert completed == []

    async def test_list_for_definition(self, db_session: AsyncSession) -> None:
        definition, version = await _definition_and_version(db_session)
        service = build_instance_service(db_session)
        await service.create(
            organization_id=definition.organization_id,
            project_id=None,
            definition_id=definition.id,
            version_id=version.id,
            trigger_type=WorkflowTriggerType.MANUAL,
            triggered_by=None,
        )
        instances = await service.list_for_definition(definition.id)
        assert len(instances) == 1

    async def test_get_active_for_definition_returns_active_instance(
        self, db_session: AsyncSession
    ) -> None:
        definition, version = await _definition_and_version(db_session)
        service = build_instance_service(db_session)
        instance = await service.create(
            organization_id=definition.organization_id,
            project_id=None,
            definition_id=definition.id,
            version_id=version.id,
            trigger_type=WorkflowTriggerType.MANUAL,
            triggered_by=None,
        )
        active = await service.get_active_for_definition(definition.id)
        assert active.id == instance.id

    async def test_get_active_for_definition_none_raises(self, db_session: AsyncSession) -> None:
        definition, _version = await _definition_and_version(db_session)
        service = build_instance_service(db_session)
        with pytest.raises(NotFoundError):
            await service.get_active_for_definition(definition.id)

    async def test_pause_resume_cancel_lifecycle(self, db_session: AsyncSession) -> None:
        definition, version = await _definition_and_version(db_session)
        service = build_instance_service(db_session)
        instance = await service.create(
            organization_id=definition.organization_id,
            project_id=None,
            definition_id=definition.id,
            version_id=version.id,
            trigger_type=WorkflowTriggerType.MANUAL,
            triggered_by=None,
        )
        paused = await service.pause(instance.id)
        assert paused.status == WorkflowInstanceStatus.PAUSED

        resumed = await service.resume(instance.id)
        assert resumed.status == WorkflowInstanceStatus.RUNNING

        cancelled = await service.cancel(instance.id)
        assert cancelled.status == WorkflowInstanceStatus.CANCELLED

    async def test_transition_on_terminal_instance_raises_conflict(
        self, db_session: AsyncSession
    ) -> None:
        definition, version = await _definition_and_version(db_session)
        service = build_instance_service(db_session)
        instance = await service.create(
            organization_id=definition.organization_id,
            project_id=None,
            definition_id=definition.id,
            version_id=version.id,
            trigger_type=WorkflowTriggerType.MANUAL,
            triggered_by=None,
        )
        await service.cancel(instance.id)
        with pytest.raises(ConflictError):
            await service.pause(instance.id)
