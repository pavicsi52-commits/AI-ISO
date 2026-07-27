"""Tests for :class:`app.services.audit.WorkflowAuditService`."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import AuditOutcome
from app.models.workflow_instance import WorkflowInstance
from app.repositories.workflow_audit import WorkflowAuditEntryRepository
from app.services.audit import WorkflowAuditService
from tests.conftest import build_version_service, make_definition, make_instance


def _build_service(db_session: AsyncSession) -> WorkflowAuditService:
    return WorkflowAuditService(WorkflowAuditEntryRepository(db_session))


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


class TestWorkflowAuditService:
    async def test_record_with_defaults(self, db_session: AsyncSession) -> None:
        service = _build_service(db_session)
        entry = await service.record(
            organization_id=uuid.uuid4(),
            instance_id=None,
            actor_id=None,
            action="create",
        )
        assert entry.outcome == AuditOutcome.SUCCESS
        assert entry.reason == ""

    async def test_record_with_before_after(self, db_session: AsyncSession) -> None:
        instance = await _linear_instance(db_session)
        service = _build_service(db_session)
        entry = await service.record(
            organization_id=instance.organization_id,
            instance_id=instance.id,
            actor_id=uuid.uuid4(),
            action="rollback",
            outcome=AuditOutcome.FAILURE,
            reason="compensation failed",
            before={"status": "running"},
            after={"status": "failed"},
        )
        assert entry.outcome == AuditOutcome.FAILURE
        assert entry.before == {"status": "running"}
        assert entry.after == {"status": "failed"}

    async def test_list_for_instance(self, db_session: AsyncSession) -> None:
        instance = await _linear_instance(db_session)
        service = _build_service(db_session)
        await service.record(
            organization_id=instance.organization_id,
            instance_id=instance.id,
            actor_id=None,
            action="create",
        )
        entries = await service.list_for_instance(instance.id)
        assert len(entries) == 1
