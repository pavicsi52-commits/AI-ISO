"""Tests for :class:`app.services.report.ConfigurationReportService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.validation import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ConfigReportType
from app.repositories.configuration_approval import ConfigurationApprovalRepository
from app.repositories.configuration_baseline import ConfigurationBaselineRepository
from app.repositories.configuration_change_set import ConfigurationChangeSetRepository
from app.repositories.configuration_compliance import ConfigurationComplianceRepository
from app.repositories.configuration_drift import ConfigurationDriftRepository
from app.repositories.configuration_profile import ConfigurationProfileRepository
from app.repositories.configuration_report import ConfigurationReportRepository
from app.repositories.configuration_rollback import ConfigurationRollbackRepository
from app.repositories.configuration_statistics import ConfigurationStatisticsRepository
from app.repositories.configuration_version import ConfigurationVersionRepository
from app.services.approval import ConfigurationApprovalService
from app.services.baseline import ConfigurationBaselineService
from app.services.compliance import ConfigurationComplianceService
from app.services.drift import ConfigurationDriftService
from app.services.report import ConfigurationReportService
from app.services.statistics import ConfigurationStatisticsService
from tests.conftest import build_profile_service, build_version_service, make_profile


def build_service(db_session: AsyncSession) -> ConfigurationReportService:
    return ConfigurationReportService(
        ConfigurationReportRepository(db_session),
        build_profile_service(db_session),
        ConfigurationComplianceService(
            ConfigurationComplianceRepository(db_session),
            ConfigurationProfileRepository(db_session),
        ),
        ConfigurationDriftService(ConfigurationDriftRepository(db_session)),
        ConfigurationBaselineService(ConfigurationBaselineRepository(db_session)),
        build_version_service(db_session),
        ConfigurationApprovalService(ConfigurationApprovalRepository(db_session)),
        ConfigurationStatisticsService(
            ConfigurationStatisticsRepository(db_session),
            ConfigurationProfileRepository(db_session),
            ConfigurationVersionRepository(db_session),
            ConfigurationDriftRepository(db_session),
            ConfigurationComplianceRepository(db_session),
            ConfigurationRollbackRepository(db_session),
            ConfigurationChangeSetRepository(db_session),
        ),
    )


async def test_generate_configuration_report(db_session: AsyncSession) -> None:
    profile = await make_profile(db_session, profile_name="reported-profile")
    service = build_service(db_session)

    report = await service.generate(
        profile.organization_id,
        report_type=ConfigReportType.CONFIGURATION,
        profile_id=profile.id,
        parameters={},
        generated_by=uuid.uuid4(),
    )

    assert report.result["profile_name"] == "reported-profile"


async def test_generate_executive_dashboard_report_needs_no_profile_id(
    db_session: AsyncSession,
) -> None:
    org_id = uuid.uuid4()
    await make_profile(db_session, organization_id=org_id)
    service = build_service(db_session)

    report = await service.generate(
        org_id,
        report_type=ConfigReportType.EXECUTIVE_DASHBOARD,
        profile_id=None,
        parameters={},
        generated_by=None,
    )

    assert "total_profiles" in report.result


async def test_generate_non_dashboard_report_requires_profile_id(db_session: AsyncSession) -> None:
    service = build_service(db_session)
    with pytest.raises(ValidationError):
        await service.generate(
            uuid.uuid4(),
            report_type=ConfigReportType.DRIFT,
            profile_id=None,
            parameters={},
            generated_by=None,
        )


async def test_list_for_org_and_for_profile(db_session: AsyncSession) -> None:
    profile = await make_profile(db_session)
    service = build_service(db_session)
    await service.generate(
        profile.organization_id,
        report_type=ConfigReportType.VERSION,
        profile_id=profile.id,
        parameters={},
        generated_by=None,
    )

    for_org = await service.list_for_org(profile.organization_id)
    assert len(for_org) == 1

    for_profile = await service.list_for_profile(profile.id)
    assert len(for_profile) == 1
