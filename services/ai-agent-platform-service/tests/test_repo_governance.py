"""Repository tests for :mod:`app.repositories.governance`.

Covers :class:`AgentStatisticRepository`, :class:`AgentReportRepository`,
and :class:`AgentAuditRepository` against real seeded Postgres rows.
"""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError

from app.models.enums import AuditAction, ReportKind
from app.models.governance import AgentAudit, AgentReport, AgentStatistic
from app.repositories.governance import (
    AgentAuditRepository,
    AgentReportRepository,
    AgentStatisticRepository,
)
from tests.conftest import ago, utcnow


def _statistic(organization_id: uuid.UUID, *, window_start=None, window_end=None) -> AgentStatistic:
    start = window_start or ago(3600)
    end = window_end or utcnow()
    return AgentStatistic(organization_id=organization_id, window_start=start, window_end=end)


def _report(
    organization_id: uuid.UUID,
    *,
    kind: ReportKind = ReportKind.EXECUTION,
    title: str = "Report",
    created_at=None,
) -> AgentReport:
    kwargs: dict[str, object] = {"organization_id": organization_id, "kind": kind, "title": title}
    if created_at is not None:
        kwargs["created_at"] = created_at
    return AgentReport(**kwargs)


def _audit(
    organization_id: uuid.UUID,
    *,
    action: AuditAction = AuditAction.ADMINISTRATIVE,
    entity_type: str = "agent",
    entity_id: uuid.UUID | None = None,
    occurred_at=None,
    summary: str = "Something happened.",
) -> AgentAudit:
    return AgentAudit(
        organization_id=organization_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        occurred_at=occurred_at or utcnow(),
        summary=summary,
    )


# ---- AgentStatisticRepository.latest ---------------------------------------------


async def test_latest_returns_most_recent_window(
    statistics_repo: AgentStatisticRepository, organization_id
):
    await statistics_repo.create(_statistic(organization_id, window_start=ago(7200)))
    most_recent = await statistics_repo.create(_statistic(organization_id, window_start=ago(60)))

    found = await statistics_repo.latest(organization_id)

    assert found is not None
    assert found.id == most_recent.id


async def test_latest_returns_none_when_no_statistics(
    statistics_repo: AgentStatisticRepository, organization_id
):
    assert await statistics_repo.latest(organization_id) is None


async def test_latest_scoped_to_org(statistics_repo: AgentStatisticRepository, organization_id):
    other_org = uuid.uuid4()
    await statistics_repo.create(_statistic(other_org))

    assert await statistics_repo.latest(organization_id) is None


# ---- AgentStatisticRepository.list_since -----------------------------------------


async def test_list_since_includes_only_windows_at_or_after(
    statistics_repo: AgentStatisticRepository, organization_id
):
    since = ago(3600)
    recent = await statistics_repo.create(_statistic(organization_id, window_start=ago(60)))
    await statistics_repo.create(_statistic(organization_id, window_start=ago(7200)))

    found = await statistics_repo.list_since(organization_id, since=since)

    assert [s.id for s in found] == [recent.id]


async def test_list_since_includes_exact_cutoff(
    statistics_repo: AgentStatisticRepository, organization_id
):
    since = ago(3600)
    at_cutoff = await statistics_repo.create(_statistic(organization_id, window_start=since))

    found = await statistics_repo.list_since(organization_id, since=since)

    assert [s.id for s in found] == [at_cutoff.id]


async def test_list_since_scoped_to_org(statistics_repo: AgentStatisticRepository, organization_id):
    other_org = uuid.uuid4()
    await statistics_repo.create(_statistic(other_org, window_start=ago(60)))

    assert await statistics_repo.list_since(organization_id, since=ago(3600)) == []


# ---- AgentReportRepository.require_in_org -----------------------------------------


async def test_report_require_in_org_returns_report(
    reports_repo: AgentReportRepository, organization_id
):
    report = await reports_repo.create(_report(organization_id))

    found = await reports_repo.require_in_org(organization_id, report.id)

    assert found.id == report.id


async def test_report_require_in_org_raises_for_other_org(
    reports_repo: AgentReportRepository, organization_id
):
    report = await reports_repo.create(_report(organization_id))

    with pytest.raises(NotFoundError):
        await reports_repo.require_in_org(uuid.uuid4(), report.id)


async def test_report_require_in_org_raises_for_unknown_id(
    reports_repo: AgentReportRepository, organization_id
):
    with pytest.raises(NotFoundError):
        await reports_repo.require_in_org(organization_id, uuid.uuid4())


# ---- AgentReportRepository.list_for_org --------------------------------------------


async def test_report_list_for_org_orders_newest_first(
    reports_repo: AgentReportRepository, organization_id
):
    older = await reports_repo.create(_report(organization_id, created_at=ago(3600)))
    newer = await reports_repo.create(_report(organization_id, created_at=ago(10)))

    found = await reports_repo.list_for_org(organization_id)

    assert [r.id for r in found] == [newer.id, older.id]


async def test_report_list_for_org_filters_by_kind(
    reports_repo: AgentReportRepository, organization_id
):
    execution_report = await reports_repo.create(
        _report(organization_id, kind=ReportKind.EXECUTION)
    )
    await reports_repo.create(_report(organization_id, kind=ReportKind.COST))

    found = await reports_repo.list_for_org(organization_id, kind=ReportKind.EXECUTION)

    assert [r.id for r in found] == [execution_report.id]
    assert found[0].kind == ReportKind.EXECUTION


async def test_report_list_for_org_scoped_to_org(
    reports_repo: AgentReportRepository, organization_id
):
    other_org = uuid.uuid4()
    await reports_repo.create(_report(other_org))

    assert await reports_repo.list_for_org(organization_id) == []


# ---- AgentAuditRepository.list_for_entity -----------------------------------------


async def test_list_for_entity_filters_by_type_and_id(
    audit_repo: AgentAuditRepository, organization_id
):
    entity_id = uuid.uuid4()
    matching = await audit_repo.create(
        _audit(organization_id, entity_type="agent", entity_id=entity_id, occurred_at=ago(60))
    )
    await audit_repo.create(
        _audit(organization_id, entity_type="task", entity_id=entity_id, occurred_at=ago(30))
    )
    await audit_repo.create(
        _audit(organization_id, entity_type="agent", entity_id=uuid.uuid4(), occurred_at=ago(10))
    )

    found = await audit_repo.list_for_entity("agent", entity_id)

    assert [a.id for a in found] == [matching.id]


async def test_list_for_entity_orders_newest_first(
    audit_repo: AgentAuditRepository, organization_id
):
    entity_id = uuid.uuid4()
    older = await audit_repo.create(
        _audit(organization_id, entity_type="agent", entity_id=entity_id, occurred_at=ago(3600))
    )
    newer = await audit_repo.create(
        _audit(organization_id, entity_type="agent", entity_id=entity_id, occurred_at=ago(10))
    )

    found = await audit_repo.list_for_entity("agent", entity_id)

    assert [a.id for a in found] == [newer.id, older.id]


# ---- AgentAuditRepository.list_for_org --------------------------------------------


async def test_audit_list_for_org_orders_newest_first_and_respects_limit(
    audit_repo: AgentAuditRepository, organization_id
):
    older = await audit_repo.create(_audit(organization_id, occurred_at=ago(3600)))
    newer = await audit_repo.create(_audit(organization_id, occurred_at=ago(10)))

    found = await audit_repo.list_for_org(organization_id)
    assert [a.id for a in found] == [newer.id, older.id]

    limited = await audit_repo.list_for_org(organization_id, limit=1)
    assert [a.id for a in limited] == [newer.id]


async def test_audit_list_for_org_scoped_to_org(audit_repo: AgentAuditRepository, organization_id):
    other_org = uuid.uuid4()
    await audit_repo.create(_audit(other_org))

    assert await audit_repo.list_for_org(organization_id) == []


# ---- AgentAuditRepository.count_by_action -----------------------------------------


async def test_count_by_action_groups_and_counts(audit_repo: AgentAuditRepository, organization_id):
    since = ago(3600)
    await audit_repo.create(
        _audit(organization_id, action=AuditAction.EXECUTED, occurred_at=ago(60))
    )
    await audit_repo.create(
        _audit(organization_id, action=AuditAction.EXECUTED, occurred_at=ago(30))
    )
    await audit_repo.create(
        _audit(organization_id, action=AuditAction.TOOL_USED, occurred_at=ago(10))
    )
    await audit_repo.create(
        _audit(organization_id, action=AuditAction.EXECUTED, occurred_at=ago(7200))
    )

    counts = await audit_repo.count_by_action(organization_id, since=since)

    assert counts == {"executed": 2, "tool_used": 1}


async def test_count_by_action_includes_exact_cutoff(
    audit_repo: AgentAuditRepository, organization_id
):
    since = ago(3600)
    await audit_repo.create(_audit(organization_id, action=AuditAction.EXECUTED, occurred_at=since))

    counts = await audit_repo.count_by_action(organization_id, since=since)

    assert counts == {"executed": 1}


async def test_count_by_action_scoped_to_org(audit_repo: AgentAuditRepository, organization_id):
    other_org = uuid.uuid4()
    await audit_repo.create(_audit(other_org, action=AuditAction.EXECUTED))

    counts = await audit_repo.count_by_action(organization_id, since=ago(3600))

    assert counts == {}


async def test_count_by_action_empty_when_none_in_window(
    audit_repo: AgentAuditRepository, organization_id
):
    await audit_repo.create(
        _audit(organization_id, action=AuditAction.EXECUTED, occurred_at=ago(7200))
    )

    counts = await audit_repo.count_by_action(organization_id, since=ago(3600))

    assert counts == {}
