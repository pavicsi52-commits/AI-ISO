"""Tests for :class:`app.services.audit.ConfigurationAuditService`."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import AuditOutcome
from app.repositories.configuration_audit import ConfigurationAuditRepository
from app.services.audit import ConfigurationAuditService
from tests.conftest import make_profile


def build_service(db_session: AsyncSession) -> ConfigurationAuditService:
    return ConfigurationAuditService(ConfigurationAuditRepository(db_session))


async def test_record_and_list_for_profile(db_session: AsyncSession) -> None:
    service = build_service(db_session)
    profile = await make_profile(db_session)
    actor_id = uuid.uuid4()

    entry = await service.record(
        profile.id,
        organization_id=profile.organization_id,
        actor_id=actor_id,
        action="create",
        after={"profile_name": "test"},
    )

    assert entry.action == "create"
    assert entry.outcome == AuditOutcome.SUCCESS
    assert entry.actor_id == actor_id

    records = await service.list_for_profile(profile.id)
    assert len(records) == 1
    assert records[0].id == entry.id


async def test_record_with_failure_outcome_and_reason(db_session: AsyncSession) -> None:
    service = build_service(db_session)
    profile = await make_profile(db_session)

    entry = await service.record(
        profile.id,
        organization_id=profile.organization_id,
        actor_id=None,
        action="delete",
        outcome=AuditOutcome.FAILURE,
        reason="Insufficient permissions.",
        before={"status": "active"},
    )

    assert entry.outcome == AuditOutcome.FAILURE
    assert entry.reason == "Insufficient permissions."
    assert entry.before == {"status": "active"}


async def test_record_with_profile_id_none(db_session: AsyncSession) -> None:
    service = build_service(db_session)

    entry = await service.record(
        None,
        organization_id=uuid.uuid4(),
        actor_id=None,
        action="bulk_export",
    )

    assert entry.profile_id is None
