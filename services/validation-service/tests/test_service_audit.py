"""Tests for :class:`app.services.audit.ValidationAuditService`."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import AuditOutcome
from app.repositories.validation_audit import ValidationAuditEntryRepository
from app.services.audit import ValidationAuditService


class TestValidationAuditService:
    async def test_record_and_list_for_org(self, db_session: AsyncSession) -> None:
        org_id = uuid.uuid4()
        service = ValidationAuditService(ValidationAuditEntryRepository(db_session))
        await service.record(
            organization_id=org_id,
            actor_id=uuid.uuid4(),
            action="create_profile",
            entity_type="ValidationProfile",
            entity_id=uuid.uuid4(),
        )
        entries = await service.list_for_org(org_id)
        assert len(entries) == 1
        assert entries[0].outcome == AuditOutcome.SUCCESS

    async def test_record_failure_outcome(self, db_session: AsyncSession) -> None:
        org_id = uuid.uuid4()
        service = ValidationAuditService(ValidationAuditEntryRepository(db_session))
        await service.record(
            organization_id=org_id,
            actor_id=None,
            action="delete_profile",
            entity_type="ValidationProfile",
            entity_id=None,
            outcome=AuditOutcome.FAILURE,
            reason="not found",
        )
        entries = await service.list_for_org(org_id)
        assert entries[0].outcome == AuditOutcome.FAILURE
