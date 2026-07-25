"""Tests for :class:`app.services.statistics.ConfigurationStatisticsService`."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import DriftType, ProfileStatus
from app.repositories.configuration_change_set import ConfigurationChangeSetRepository
from app.repositories.configuration_compliance import ConfigurationComplianceRepository
from app.repositories.configuration_drift import ConfigurationDriftRepository
from app.repositories.configuration_profile import ConfigurationProfileRepository
from app.repositories.configuration_rollback import ConfigurationRollbackRepository
from app.repositories.configuration_statistics import ConfigurationStatisticsRepository
from app.repositories.configuration_version import ConfigurationVersionRepository
from app.services.drift import ConfigurationDriftService
from app.services.statistics import ConfigurationStatisticsService
from tests.conftest import make_profile


def build_service(db_session: AsyncSession) -> ConfigurationStatisticsService:
    return ConfigurationStatisticsService(
        ConfigurationStatisticsRepository(db_session),
        ConfigurationProfileRepository(db_session),
        ConfigurationVersionRepository(db_session),
        ConfigurationDriftRepository(db_session),
        ConfigurationComplianceRepository(db_session),
        ConfigurationRollbackRepository(db_session),
        ConfigurationChangeSetRepository(db_session),
    )


async def test_get_for_org_computes_when_missing(db_session: AsyncSession) -> None:
    org_id = uuid.uuid4()
    await make_profile(db_session, organization_id=org_id, status=ProfileStatus.ACTIVE)
    await make_profile(db_session, organization_id=org_id, status=ProfileStatus.DRAFT)

    service = build_service(db_session)
    snapshot = await service.get_for_org(org_id)

    assert snapshot.total_profiles == 2
    assert snapshot.deployment_readiness["active_profiles"] == 1
    assert snapshot.deployment_readiness["draft_profiles"] == 1


async def test_get_for_org_returns_cached_snapshot_on_second_call(
    db_session: AsyncSession,
) -> None:
    org_id = uuid.uuid4()
    await make_profile(db_session, organization_id=org_id)

    service = build_service(db_session)
    first = await service.get_for_org(org_id)
    second = await service.get_for_org(org_id)

    assert first.id == second.id


async def test_recompute_includes_drift_statistics(db_session: AsyncSession) -> None:
    profile = await make_profile(db_session)
    drift_service = ConfigurationDriftService(ConfigurationDriftRepository(db_session))
    await drift_service.report(
        organization_id=profile.organization_id,
        profile_id=profile.id,
        managed_asset_id=uuid.uuid4(),
        drift_type=DriftType.POLICY_DRIFT,
        details={},
    )

    service = build_service(db_session)
    snapshot = await service.recompute(profile.organization_id)

    assert snapshot.drift_statistics["unresolved_total"] == 1


async def test_recompute_updates_existing_snapshot_in_place(db_session: AsyncSession) -> None:
    org_id = uuid.uuid4()
    await make_profile(db_session, organization_id=org_id)
    service = build_service(db_session)

    first = await service.recompute(org_id)
    await make_profile(db_session, organization_id=org_id)
    second = await service.recompute(org_id)

    assert first.id == second.id
    assert second.total_profiles == 2
