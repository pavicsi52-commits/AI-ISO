"""Tests for :class:`app.services.job.AutomationJobService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.events.base import DomainEvent
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.automation_events import AutomationCreatedEvent
from app.models.enums import AutomationType, ExecutionMode, JobStatus, PlaybookType
from tests.conftest import build_job_service, make_job


class TestAutomationJobService:
    async def test_create_publishes_event_and_records_audit(self, db_session: AsyncSession) -> None:
        published: list[DomainEvent] = []

        async def _publish(event: DomainEvent) -> None:
            published.append(event)

        service = build_job_service(db_session, publish_event=_publish)
        org_id = uuid.uuid4()
        job = await service.create(
            organization_id=org_id,
            project_id=None,
            name="deploy-web",
            description="Deploys the web tier",
            automation_type=AutomationType.DEPLOYMENT,
            playbook_type=PlaybookType.SHELL_SCRIPT,
            execution_mode=ExecutionMode.MANUAL,
            content="echo deploy",
            target_selector={},
            variables={},
            tags=["prod"],
            timeout_seconds=600,
            owner_id=None,
            created_by=uuid.uuid4(),
        )
        assert job.name == "deploy-web"
        assert job.status == JobStatus.ACTIVE
        assert len(published) == 1
        assert isinstance(published[0], AutomationCreatedEvent)

        audit_entries = await service._audit.list_for_job(job.id)
        assert len(audit_entries) == 1
        assert audit_entries[0].action == "create"

    async def test_create_without_publish_event_does_not_raise(
        self, db_session: AsyncSession
    ) -> None:
        service = build_job_service(db_session)
        job = await service.create(
            organization_id=uuid.uuid4(),
            project_id=None,
            name="no-publish",
            description=None,
            automation_type=AutomationType.CUSTOM_AUTOMATION,
            playbook_type=PlaybookType.BASH,
            execution_mode=ExecutionMode.MANUAL,
            content="echo hi",
            target_selector={},
            variables={},
            tags=[],
            timeout_seconds=None,
            owner_id=None,
            created_by=None,
        )
        assert job.id is not None

    async def test_get_by_id_missing_raises(self, db_session: AsyncSession) -> None:
        service = build_job_service(db_session)
        with pytest.raises(NotFoundError):
            await service.get_by_id(uuid.uuid4())

    async def test_list_for_org(self, db_session: AsyncSession) -> None:
        org_id = uuid.uuid4()
        await make_job(db_session, organization_id=org_id, name="j1")
        await make_job(db_session, organization_id=org_id, name="j2")
        service = build_job_service(db_session)
        jobs = await service.list_for_org(org_id)
        assert {j.name for j in jobs} == {"j1", "j2"}

    async def test_search(self, db_session: AsyncSession) -> None:
        org_id = uuid.uuid4()
        await make_job(db_session, organization_id=org_id, name="patch-linux")
        service = build_job_service(db_session)
        result = await service.search(
            query="patch", filters=None, sort_fields=None, page=1, page_size=10
        )
        assert result.metadata.total >= 1

    async def test_update_records_audit(self, db_session: AsyncSession) -> None:
        job = await make_job(db_session)
        service = build_job_service(db_session)
        updated = await service.update(
            job.id,
            actor_id=uuid.uuid4(),
            name="renamed",
            description="new desc",
            status=JobStatus.DISABLED,
            automation_type=job.automation_type,
            playbook_type=job.playbook_type,
            execution_mode=job.execution_mode,
            content="echo updated",
            target_selector={},
            variables={},
            tags=[],
            timeout_seconds=None,
            owner_id=None,
        )
        assert updated.name == "renamed"
        assert updated.status == JobStatus.DISABLED

        audit_entries = await service._audit.list_for_job(job.id)
        assert any(entry.action == "update" for entry in audit_entries)

    async def test_delete_records_audit(self, db_session: AsyncSession) -> None:
        job = await make_job(db_session)
        service = build_job_service(db_session)
        await service.delete(job.id, actor_id=uuid.uuid4())
        with pytest.raises(NotFoundError):
            await service.get_by_id(job.id)
        audit_entries = await service._audit.list_for_job(job.id)
        assert any(entry.action == "delete" for entry in audit_entries)
