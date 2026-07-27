"""Tests for :class:`app.services.statistics.PlaybookStatisticsService`."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ContentType, PlaybookStatus
from app.repositories.playbook import PlaybookRepository
from app.repositories.playbook_approval import PlaybookApprovalRepository
from app.repositories.playbook_statistics import PlaybookStatisticsRepository
from app.repositories.playbook_version import PlaybookVersionRepository
from app.services.statistics import PlaybookStatisticsService
from tests.conftest import build_version_service, make_playbook


def _build_service(db_session: AsyncSession) -> PlaybookStatisticsService:
    return PlaybookStatisticsService(
        PlaybookStatisticsRepository(db_session),
        PlaybookRepository(db_session),
        PlaybookVersionRepository(db_session),
        PlaybookApprovalRepository(db_session),
    )


class TestPlaybookStatisticsService:
    async def test_recompute_with_no_playbooks(self, db_session: AsyncSession) -> None:
        org_id = uuid.uuid4()
        service = _build_service(db_session)
        snapshot = await service.recompute(org_id)
        assert snapshot.total_playbooks == 0
        assert snapshot.total_versions == 0
        assert snapshot.total_downloads == 0

    async def test_recompute_counts_playbooks_versions_and_deprecated(
        self, db_session: AsyncSession
    ) -> None:
        org_id = uuid.uuid4()
        version_service = build_version_service(db_session)

        active = await make_playbook(
            db_session, organization_id=org_id, name="active", content_type=ContentType.SHELL_SCRIPT
        )
        await version_service.create_version(
            active.id, content="echo hi", release_notes=None, change_summary=None, changed_by=None
        )
        deprecated = await make_playbook(
            db_session,
            organization_id=org_id,
            name="deprecated",
            status=PlaybookStatus.DEPRECATED,
            content_type=ContentType.SHELL_SCRIPT,
        )
        await version_service.create_version(
            deprecated.id,
            content="echo bye",
            release_notes=None,
            change_summary=None,
            changed_by=None,
        )

        service = _build_service(db_session)
        snapshot = await service.recompute(org_id)
        assert snapshot.total_playbooks == 2
        assert snapshot.total_versions == 2
        assert snapshot.deprecated_content_count == 1
        assert snapshot.validation_results_summary.get("passed") == 2

    async def test_get_for_org_recomputes_when_absent_then_returns_cached(
        self, db_session: AsyncSession
    ) -> None:
        org_id = uuid.uuid4()
        service = _build_service(db_session)

        first = await service.get_for_org(org_id)
        assert first.total_playbooks == 0

        await make_playbook(db_session, organization_id=org_id, name="new-one")
        cached = await service.get_for_org(org_id)
        assert cached.id == first.id
        assert cached.total_playbooks == 0

        refreshed = await service.recompute(org_id)
        assert refreshed.id == first.id
        assert refreshed.total_playbooks == 1
