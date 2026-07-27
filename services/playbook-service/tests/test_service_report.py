"""Tests for :class:`app.services.report.PlaybookReportService`."""

from __future__ import annotations

import uuid
from uuid import UUID

import pytest
from shared_core.exceptions.validation import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import (
    ApprovalStatus,
    ApprovalType,
    ContentType,
    DependencyType,
    PlaybookReportType,
)
from app.models.playbook import Playbook
from app.repositories.playbook import PlaybookRepository
from app.repositories.playbook_approval import PlaybookApprovalRepository
from app.repositories.playbook_dependency import PlaybookDependencyRepository
from app.repositories.playbook_report import PlaybookReportRepository
from app.repositories.playbook_statistics import PlaybookStatisticsRepository
from app.repositories.playbook_version import PlaybookVersionRepository
from app.services.approval import PlaybookApprovalService
from app.services.dependency import PlaybookDependencyService
from app.services.report import PlaybookReportService
from app.services.statistics import PlaybookStatisticsService
from tests.conftest import build_playbook_service, build_version_service


def _build_service(db_session: AsyncSession) -> PlaybookReportService:
    return PlaybookReportService(
        PlaybookReportRepository(db_session),
        build_playbook_service(db_session),
        build_version_service(db_session),
        PlaybookDependencyService(
            PlaybookDependencyRepository(db_session), PlaybookRepository(db_session)
        ),
        PlaybookApprovalService(
            PlaybookApprovalRepository(db_session), PlaybookRepository(db_session)
        ),
        PlaybookStatisticsService(
            PlaybookStatisticsRepository(db_session),
            PlaybookRepository(db_session),
            PlaybookVersionRepository(db_session),
            PlaybookApprovalRepository(db_session),
        ),
    )


async def _create_playbook(db_session: AsyncSession, *, organization_id: UUID) -> Playbook:
    playbook_service = build_playbook_service(db_session)
    return await playbook_service.create(
        organization_id=organization_id,
        project_id=None,
        name="p1",
        display_name=None,
        description=None,
        content_type=ContentType.SHELL_SCRIPT,
        category_id=None,
        repository_id=None,
        owner_id=None,
        author_id=None,
        entry_file=None,
        metadata={},
        initial_content="echo hi",
        created_by=None,
    )


class TestPlaybookReportService:
    async def test_generate_repository_report(self, db_session: AsyncSession) -> None:
        org_id = uuid.uuid4()
        await _create_playbook(db_session, organization_id=org_id)
        service = _build_service(db_session)
        report = await service.generate(
            org_id,
            report_type=PlaybookReportType.REPOSITORY,
            playbook_id=None,
            parameters={},
            generated_by=None,
        )
        assert report.result["total_playbooks"] == 1

    async def test_generate_executive_dashboard_report(self, db_session: AsyncSession) -> None:
        org_id = uuid.uuid4()
        service = _build_service(db_session)
        report = await service.generate(
            org_id,
            report_type=PlaybookReportType.EXECUTIVE_DASHBOARD,
            playbook_id=None,
            parameters={},
            generated_by=None,
        )
        assert report.result["total_playbooks"] == 0

    async def test_generate_validation_report_requires_playbook_id(
        self, db_session: AsyncSession
    ) -> None:
        service = _build_service(db_session)
        with pytest.raises(ValidationError):
            await service.generate(
                uuid.uuid4(),
                report_type=PlaybookReportType.VALIDATION,
                playbook_id=None,
                parameters={},
                generated_by=None,
            )

    async def test_generate_validation_report(self, db_session: AsyncSession) -> None:
        org_id = uuid.uuid4()
        playbook = await _create_playbook(db_session, organization_id=org_id)
        service = _build_service(db_session)
        report = await service.generate(
            org_id,
            report_type=PlaybookReportType.VALIDATION,
            playbook_id=playbook.id,
            parameters={},
            generated_by=None,
        )
        assert report.result["has_content"] is True
        assert report.result["valid"] is True

    async def test_generate_approval_report(self, db_session: AsyncSession) -> None:
        org_id = uuid.uuid4()
        playbook = await _create_playbook(db_session, organization_id=org_id)
        approval_service = PlaybookApprovalService(
            PlaybookApprovalRepository(db_session), PlaybookRepository(db_session)
        )
        await approval_service.request(
            playbook.id,
            version_id=None,
            approval_type=ApprovalType.TECHNICAL,
            level=1,
            requested_by=None,
        )
        service = _build_service(db_session)
        report = await service.generate(
            org_id,
            report_type=PlaybookReportType.APPROVAL,
            playbook_id=playbook.id,
            parameters={},
            generated_by=None,
        )
        assert report.result["total_approvals"] == 1
        assert report.result["by_status"] == {str(ApprovalStatus.PENDING): 1}

    async def test_generate_version_report(self, db_session: AsyncSession) -> None:
        org_id = uuid.uuid4()
        playbook = await _create_playbook(db_session, organization_id=org_id)
        service = _build_service(db_session)
        report = await service.generate(
            org_id,
            report_type=PlaybookReportType.VERSION,
            playbook_id=playbook.id,
            parameters={},
            generated_by=None,
        )
        assert report.result["total_versions"] == 1
        assert report.result["latest_version_number"] == "1.0.0"

    async def test_generate_dependency_report(self, db_session: AsyncSession) -> None:
        org_id = uuid.uuid4()
        playbook = await _create_playbook(db_session, organization_id=org_id)
        dependency_service = PlaybookDependencyService(
            PlaybookDependencyRepository(db_session), PlaybookRepository(db_session)
        )
        await dependency_service.create(
            playbook.id,
            dependency_type=DependencyType.PYTHON_PACKAGE,
            name="requests",
            version_constraint=">=2.0",
        )
        service = _build_service(db_session)
        report = await service.generate(
            org_id,
            report_type=PlaybookReportType.DEPENDENCY,
            playbook_id=playbook.id,
            parameters={},
            generated_by=None,
        )
        assert report.result["total_dependencies"] == 1
        assert report.result["by_type"] == {str(DependencyType.PYTHON_PACKAGE): 1}

    async def test_list_for_org_and_for_playbook(self, db_session: AsyncSession) -> None:
        org_id = uuid.uuid4()
        service = _build_service(db_session)
        await service.generate(
            org_id,
            report_type=PlaybookReportType.REPOSITORY,
            playbook_id=None,
            parameters={},
            generated_by=None,
        )
        reports = await service.list_for_org(org_id)
        assert len(reports) == 1
        assert await service.list_for_org(org_id, report_type=PlaybookReportType.VALIDATION) == []
        assert await service.list_for_playbook(uuid.uuid4()) == []
