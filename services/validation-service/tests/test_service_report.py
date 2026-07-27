"""Tests for :class:`app.services.report.ValidationReportService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.validation import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ValidationReportType
from app.repositories.validation_execution import ValidationExecutionRepository
from app.repositories.validation_failure import ValidationFailureRepository
from app.repositories.validation_history import ValidationHistoryRepository
from app.repositories.validation_profile import ValidationProfileRepository
from app.repositories.validation_report import ValidationReportRepository
from app.repositories.validation_result import ValidationResultRepository
from app.repositories.validation_statistics import ValidationStatisticsRepository
from app.services.report import ValidationReportService
from app.services.statistics import ValidationStatisticsService
from tests.conftest import make_check, make_execution, make_profile, make_target


def _service(db_session: AsyncSession) -> ValidationReportService:
    statistics = ValidationStatisticsService(
        ValidationStatisticsRepository(db_session),
        ValidationProfileRepository(db_session),
        ValidationExecutionRepository(db_session),
        ValidationFailureRepository(db_session),
        ValidationHistoryRepository(db_session),
    )
    return ValidationReportService(
        ValidationReportRepository(db_session),
        ValidationExecutionRepository(db_session),
        ValidationResultRepository(db_session),
        ValidationFailureRepository(db_session),
        ValidationHistoryRepository(db_session),
        statistics,
    )


class TestValidationReportService:
    async def test_execution_report_requires_execution_id(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        with pytest.raises(ValidationError, match="execution_id"):
            await service.generate(
                uuid.uuid4(),
                report_type=ValidationReportType.VALIDATION,
                execution_id=None,
                target_id=None,
                parameters={},
                generated_by=None,
            )

    async def test_asset_report_requires_target_id(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        with pytest.raises(ValidationError, match="target_id"):
            await service.generate(
                uuid.uuid4(),
                report_type=ValidationReportType.ASSET,
                execution_id=None,
                target_id=None,
                parameters={},
                generated_by=None,
            )

    async def test_execution_report(self, db_session: AsyncSession) -> None:
        org_id = uuid.uuid4()
        check = await make_check(db_session, organization_id=org_id)
        profile = await make_profile(db_session, organization_id=org_id, check_ids=[check.id])
        target = await make_target(db_session, organization_id=org_id)
        execution = await make_execution(db_session, profile, [target])
        service = _service(db_session)
        report = await service.generate(
            org_id,
            report_type=ValidationReportType.VALIDATION,
            execution_id=execution.id,
            target_id=None,
            parameters={},
            generated_by=None,
        )
        assert "total_results" in report.result

    async def test_compliance_report(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        report = await service.generate(
            uuid.uuid4(),
            report_type=ValidationReportType.COMPLIANCE,
            execution_id=None,
            target_id=None,
            parameters={},
            generated_by=None,
        )
        assert "total_unresolved_failures" in report.result

    async def test_security_report(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        report = await service.generate(
            uuid.uuid4(),
            report_type=ValidationReportType.SECURITY,
            execution_id=None,
            target_id=None,
            parameters={},
            generated_by=None,
        )
        assert "by_severity" in report.result

    async def test_executive_report(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        report = await service.generate(
            uuid.uuid4(),
            report_type=ValidationReportType.EXECUTIVE,
            execution_id=None,
            target_id=None,
            parameters={},
            generated_by=None,
        )
        assert "pass_rate" in report.result

    async def test_operational_report(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        report = await service.generate(
            uuid.uuid4(),
            report_type=ValidationReportType.OPERATIONAL,
            execution_id=None,
            target_id=None,
            parameters={},
            generated_by=None,
        )
        assert "average_duration_seconds" in report.result

    async def test_trend_report(self, db_session: AsyncSession) -> None:
        service = _service(db_session)
        report = await service.generate(
            uuid.uuid4(),
            report_type=ValidationReportType.TREND,
            execution_id=None,
            target_id=None,
            parameters={},
            generated_by=None,
        )
        assert "trend_data" in report.result

    async def test_asset_report(self, db_session: AsyncSession) -> None:
        org_id = uuid.uuid4()
        target = await make_target(db_session, organization_id=org_id)
        service = _service(db_session)
        report = await service.generate(
            org_id,
            report_type=ValidationReportType.ASSET,
            execution_id=None,
            target_id=target.id,
            parameters={},
            generated_by=None,
        )
        assert "total_snapshots" in report.result

    async def test_list_for_org(self, db_session: AsyncSession) -> None:
        org_id = uuid.uuid4()
        service = _service(db_session)
        await service.generate(
            org_id,
            report_type=ValidationReportType.TREND,
            execution_id=None,
            target_id=None,
            parameters={},
            generated_by=None,
        )
        reports = await service.list_for_org(org_id)
        assert len(reports) == 1
