"""Repository tests for ``PluginStatisticRepository``, ``PluginReportRepository``,
and ``PluginAuditRepository``.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from shared_core.exceptions.not_found import NotFoundError

from app.models.enums import AuditAction, ReportKind
from app.models.governance import PluginAudit, PluginReport, PluginStatistic
from app.repositories.governance import (
    PluginAuditRepository,
    PluginReportRepository,
    PluginStatisticRepository,
)
from tests.conftest import ago, utcnow


def _statistic(
    organization_id: uuid.UUID,
    *,
    window_start: datetime,
    window_end: datetime,
    **kwargs: object,
) -> PluginStatistic:
    defaults: dict[str, object] = {
        "organization_id": organization_id,
        "window_start": window_start,
        "window_end": window_end,
    }
    defaults.update(kwargs)
    return PluginStatistic(**defaults)


def _report(
    organization_id: uuid.UUID,
    *,
    kind: ReportKind = ReportKind.MARKETPLACE,
    title: str = "Report",
    **kwargs: object,
) -> PluginReport:
    defaults: dict[str, object] = {
        "organization_id": organization_id,
        "kind": kind,
        "title": title,
    }
    defaults.update(kwargs)
    return PluginReport(**defaults)


def _audit(
    organization_id: uuid.UUID,
    *,
    action: AuditAction = AuditAction.PLUGIN_REGISTERED,
    entity_type: str = "plugin",
    **kwargs: object,
) -> PluginAudit:
    defaults: dict[str, object] = {
        "organization_id": organization_id,
        "action": action,
        "entity_type": entity_type,
        "occurred_at": utcnow(),
        "summary": "Test audit entry",
    }
    defaults.update(kwargs)
    return PluginAudit(**defaults)


class TestPluginStatisticRepository:
    async def test_create_and_require_by_id_round_trip(
        self, statistics_repo: PluginStatisticRepository, organization_id: uuid.UUID
    ) -> None:
        now = utcnow()
        created = await statistics_repo.create(
            _statistic(organization_id, window_start=now, window_end=now + timedelta(hours=1))
        )
        fetched = await statistics_repo.require_by_id(created.id)
        assert fetched.id == created.id

    async def test_get_for_window_hit(
        self, statistics_repo: PluginStatisticRepository, organization_id: uuid.UUID
    ) -> None:
        window_start = ago(3600)
        stat = await statistics_repo.create(
            _statistic(organization_id, window_start=window_start, window_end=ago(0))
        )

        found = await statistics_repo.get_for_window(organization_id, window_start)
        assert found is not None
        assert found.id == stat.id

    async def test_get_for_window_miss(
        self, statistics_repo: PluginStatisticRepository, organization_id: uuid.UUID
    ) -> None:
        assert await statistics_repo.get_for_window(organization_id, utcnow()) is None

    async def test_get_for_window_miss_wrong_org(
        self, statistics_repo: PluginStatisticRepository, organization_id: uuid.UUID
    ) -> None:
        window_start = ago(3600)
        await statistics_repo.create(
            _statistic(organization_id, window_start=window_start, window_end=ago(0))
        )

        assert await statistics_repo.get_for_window(uuid.uuid4(), window_start) is None

    async def test_latest(
        self, statistics_repo: PluginStatisticRepository, organization_id: uuid.UUID
    ) -> None:
        await statistics_repo.create(
            _statistic(organization_id, window_start=ago(7200), window_end=ago(3600))
        )
        newer = await statistics_repo.create(
            _statistic(organization_id, window_start=ago(3600), window_end=ago(0))
        )

        found = await statistics_repo.latest(organization_id)
        assert found is not None
        assert found.id == newer.id

    async def test_latest_miss(
        self, statistics_repo: PluginStatisticRepository, organization_id: uuid.UUID
    ) -> None:
        assert await statistics_repo.latest(organization_id) is None

    async def test_list_since(
        self, statistics_repo: PluginStatisticRepository, organization_id: uuid.UUID
    ) -> None:
        since = ago(5000)
        await statistics_repo.create(
            _statistic(organization_id, window_start=ago(9000), window_end=ago(8000))
        )
        included_a = await statistics_repo.create(
            _statistic(organization_id, window_start=ago(4000), window_end=ago(3000))
        )
        included_b = await statistics_repo.create(
            _statistic(organization_id, window_start=ago(1000), window_end=ago(0))
        )

        found = await statistics_repo.list_since(organization_id, since=since)
        assert [s.id for s in found] == [included_a.id, included_b.id]

    async def test_list_since_empty(
        self, statistics_repo: PluginStatisticRepository, organization_id: uuid.UUID
    ) -> None:
        assert await statistics_repo.list_since(organization_id, since=utcnow()) == []


class TestPluginReportRepository:
    async def test_create_and_require_by_id_round_trip(
        self, reports_repo: PluginReportRepository, organization_id: uuid.UUID
    ) -> None:
        created = await reports_repo.create(_report(organization_id))
        fetched = await reports_repo.require_by_id(created.id)
        assert fetched.id == created.id

    async def test_require_in_org_hit(
        self, reports_repo: PluginReportRepository, organization_id: uuid.UUID
    ) -> None:
        report = await reports_repo.create(_report(organization_id))
        found = await reports_repo.require_in_org(organization_id, report.id)
        assert found.id == report.id

    async def test_require_in_org_miss_unknown_id(
        self, reports_repo: PluginReportRepository, organization_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError):
            await reports_repo.require_in_org(organization_id, uuid.uuid4())

    async def test_require_in_org_miss_wrong_org(
        self, reports_repo: PluginReportRepository, organization_id: uuid.UUID
    ) -> None:
        report = await reports_repo.create(_report(organization_id))
        with pytest.raises(NotFoundError):
            await reports_repo.require_in_org(uuid.uuid4(), report.id)

    async def test_list_for_org_kind_filter(
        self, reports_repo: PluginReportRepository, organization_id: uuid.UUID
    ) -> None:
        marketplace_report = await reports_repo.create(
            _report(organization_id, kind=ReportKind.MARKETPLACE, title="Marketplace")
        )
        await reports_repo.create(_report(organization_id, kind=ReportKind.SECURITY, title="Security"))

        found = await reports_repo.list_for_org(organization_id, kind=ReportKind.MARKETPLACE)
        assert [r.id for r in found] == [marketplace_report.id]

        found_all = await reports_repo.list_for_org(organization_id)
        assert len(found_all) == 2

    async def test_list_for_org_empty(
        self, reports_repo: PluginReportRepository, organization_id: uuid.UUID
    ) -> None:
        assert await reports_repo.list_for_org(organization_id) == []


class TestPluginAuditRepository:
    async def test_create_and_require_by_id_round_trip(
        self, audit_repo: PluginAuditRepository, organization_id: uuid.UUID
    ) -> None:
        created = await audit_repo.create(_audit(organization_id))
        fetched = await audit_repo.require_by_id(created.id)
        assert fetched.id == created.id

    async def test_list_for_entity(
        self, audit_repo: PluginAuditRepository, organization_id: uuid.UUID
    ) -> None:
        entity_id = uuid.uuid4()
        older = await audit_repo.create(
            _audit(organization_id, entity_type="plugin", entity_id=entity_id, occurred_at=ago(300))
        )
        newer = await audit_repo.create(
            _audit(organization_id, entity_type="plugin", entity_id=entity_id, occurred_at=ago(10))
        )
        await audit_repo.create(
            _audit(
                organization_id, entity_type="installation", entity_id=entity_id, occurred_at=ago(50)
            )
        )
        await audit_repo.create(
            _audit(organization_id, entity_type="plugin", entity_id=uuid.uuid4(), occurred_at=ago(20))
        )

        found = await audit_repo.list_for_entity("plugin", entity_id)
        assert [a.id for a in found] == [newer.id, older.id]

    async def test_list_for_entity_empty(self, audit_repo: PluginAuditRepository) -> None:
        assert await audit_repo.list_for_entity("plugin", uuid.uuid4()) == []

    async def test_list_for_org_action_filter(
        self, audit_repo: PluginAuditRepository, organization_id: uuid.UUID
    ) -> None:
        registered = await audit_repo.create(
            _audit(organization_id, action=AuditAction.PLUGIN_REGISTERED)
        )
        await audit_repo.create(_audit(organization_id, action=AuditAction.PLUGIN_INSTALLED))

        found = await audit_repo.list_for_org(organization_id, action=AuditAction.PLUGIN_REGISTERED)
        assert [a.id for a in found] == [registered.id]

        found_all = await audit_repo.list_for_org(organization_id)
        assert len(found_all) == 2

    async def test_list_for_org_empty(
        self, audit_repo: PluginAuditRepository, organization_id: uuid.UUID
    ) -> None:
        assert await audit_repo.list_for_org(organization_id) == []

    async def test_count_by_action_grouping(
        self, audit_repo: PluginAuditRepository, organization_id: uuid.UUID
    ) -> None:
        since = ago(3600)
        await audit_repo.create(
            _audit(organization_id, action=AuditAction.PLUGIN_REGISTERED, occurred_at=ago(100))
        )
        await audit_repo.create(
            _audit(organization_id, action=AuditAction.PLUGIN_REGISTERED, occurred_at=ago(200))
        )
        await audit_repo.create(
            _audit(organization_id, action=AuditAction.PLUGIN_INSTALLED, occurred_at=ago(50))
        )
        # Older than `since` -- must be excluded from the aggregate.
        await audit_repo.create(
            _audit(organization_id, action=AuditAction.PLUGIN_ACTIVATED, occurred_at=ago(7000))
        )

        counts = await audit_repo.count_by_action(organization_id, since=since)
        assert counts == {"plugin_registered": 2, "plugin_installed": 1}

    async def test_count_by_action_empty(
        self, audit_repo: PluginAuditRepository, organization_id: uuid.UUID
    ) -> None:
        assert await audit_repo.count_by_action(organization_id, since=ago(3600)) == {}
