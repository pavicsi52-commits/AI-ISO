"""Tests for :class:`app.services.audit.PlaybookAuditService`."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import AuditOutcome
from tests.conftest import build_audit_service, make_playbook


class TestPlaybookAuditService:
    async def test_record_and_list_for_playbook(self, db_session: AsyncSession) -> None:
        playbook = await make_playbook(db_session)
        service = build_audit_service(db_session)
        entry = await service.record(
            playbook_id=playbook.id,
            organization_id=playbook.organization_id,
            actor_id=uuid.uuid4(),
            action="create",
            after={"name": playbook.name},
        )
        assert entry.action == "create"
        assert entry.outcome == AuditOutcome.SUCCESS

        entries = await service.list_for_playbook(playbook.id)
        assert len(entries) == 1
        assert entries[0].id == entry.id

    async def test_record_with_failure_outcome(self, db_session: AsyncSession) -> None:
        playbook = await make_playbook(db_session)
        service = build_audit_service(db_session)
        entry = await service.record(
            playbook_id=playbook.id,
            organization_id=playbook.organization_id,
            actor_id=None,
            action="delete",
            outcome=AuditOutcome.FAILURE,
            reason="denied",
        )
        assert entry.outcome == AuditOutcome.FAILURE
        assert entry.reason == "denied"

    async def test_list_for_playbook_empty(self, db_session: AsyncSession) -> None:
        service = build_audit_service(db_session)
        assert await service.list_for_playbook(uuid.uuid4()) == []
