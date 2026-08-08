"""Tests for :mod:`app.services.reporting` -- ``StatisticsService``,
``ReportService``, and ``AuditService``.

Every aggregate is checked against rows this test actually seeded, so
the assertions are exact numbers rather than "something was counted".

``ReportService.generate`` documents that a build failure is *recorded*
on the row rather than raised, and reaching that branch needs a
genuinely failing read. It is produced here without any mock, by
handing the service one real repository bound to a real engine pointed
at a dead loopback port (``127.0.0.1:1``) -- the same "genuinely
unreachable, fails fast" technique ``tests/test_clients.py`` and
``tests/test_tool_execution.py`` already use. The report repository
keeps the healthy session, so the ``FAILED`` row is still written.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from shared_core.config.settings import DatabaseSettings
from shared_core.database.engine import create_engine
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import (
    AgentType,
    AuditAction,
    ExecutionStatus,
    MemoryScope,
    ModelProvider,
    ReasoningMode,
    ReportFormat,
    ReportKind,
    ReportStatus,
)
from app.models.execution import AgentExecution
from app.repositories.agent import AgentRepository
from app.services.agent import ProfileFields
from app.services.reporting import ReportService
from tests.conftest import ago, soon, utcnow


async def _execution(
    executions_repo,
    agent,
    *,
    status: ExecutionStatus = ExecutionStatus.COMPLETED,
    total_tokens: int = 0,
    cost_usd: float = 0.0,
    latency_ms: float | None = None,
    provider: ModelProvider = ModelProvider.OLLAMA,
    trace: list[dict[str, object]] | None = None,
    started_at=None,
) -> AgentExecution:
    """Seed one real execution row for *agent*."""
    return await executions_repo.create(
        AgentExecution(
            organization_id=agent.organization_id,
            agent_id=agent.id,
            status=status,
            reasoning_mode=ReasoningMode.TOOL_BASED,
            model_provider=provider,
            model_name="llama3",
            total_tokens=total_tokens,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            trace=trace or [],
            started_at=started_at or utcnow(),
        )
    )


@pytest_asyncio.fixture
async def unreachable_agents_repo() -> AsyncIterator[AgentRepository]:
    """A real ``AgentRepository`` on a real engine pointed at a dead
    loopback port -- every query fails fast, for real."""
    engine = create_engine(
        DatabaseSettings(
            database_host="127.0.0.1",
            database_port=1,
            database_name="aiios_ai_agent_platform",
            database_user="aiios",
            database_password="change-me",
            _env_file=None,
        )
    )
    session = AsyncSession(engine)
    try:
        yield AgentRepository(session)
    finally:
        await session.close()
        await engine.dispose()


# ---------------------------------------------------------------------------
# StatisticsService.rollup
# ---------------------------------------------------------------------------


class TestRollup:
    async def test_counts_agents_by_status_and_type(
        self, statistics_service, agent_service, make_agent, organization_id
    ) -> None:
        await make_agent(slug="one", agent_type=AgentType.EXECUTOR)
        await make_agent(slug="two", agent_type=AgentType.EXECUTOR)
        paused = await make_agent(slug="three", agent_type=AgentType.PLANNER)
        await agent_service.pause(paused)

        window = await statistics_service.rollup(
            organization_id, window_start=ago(3600), window_end=soon(3600)
        )

        assert window.active_agents == 2
        assert window.by_agent_type == {"executor": 2, "planner": 1}

    async def test_counts_tasks_created_inside_the_window(
        self, statistics_service, task_service, organization_id
    ) -> None:
        for index in range(3):
            await task_service.create_task(
                organization_id=organization_id, task_type=f"t{index}", payload={}
            )

        window = await statistics_service.rollup(
            organization_id, window_start=ago(3600), window_end=soon(3600)
        )

        assert window.task_count == 3

    async def test_excludes_everything_outside_the_window(
        self, statistics_service, task_service, executions_repo, make_agent, organization_id
    ) -> None:
        agent = await make_agent(slug="outside")
        await task_service.create_task(organization_id=organization_id, task_type="now", payload={})
        await _execution(executions_repo, agent)

        window = await statistics_service.rollup(
            organization_id, window_start=ago(7200), window_end=ago(3600)
        )

        assert window.task_count == 0
        assert window.executions_succeeded == 0
        assert window.executions_failed == 0
        assert window.total_tokens == 0
        assert window.memory_rows_created == 0
        assert window.by_model_provider == {}
        assert window.by_tool == {}

    async def test_aggregates_execution_outcomes_exactly(
        self, statistics_service, executions_repo, make_agent, organization_id
    ) -> None:
        agent = await make_agent(slug="aggregated")
        await _execution(executions_repo, agent, total_tokens=10, cost_usd=0.5, latency_ms=100.0)
        await _execution(executions_repo, agent, total_tokens=20, cost_usd=1.5, latency_ms=200.0)
        await _execution(
            executions_repo,
            agent,
            status=ExecutionStatus.FAILED,
            total_tokens=30,
            provider=ModelProvider.ANTHROPIC,
        )

        window = await statistics_service.rollup(
            organization_id, window_start=ago(3600), window_end=soon(3600)
        )

        assert window.executions_succeeded == 2
        assert window.executions_failed == 1
        assert window.total_tokens == 60
        assert window.average_cost_usd == 1.0
        assert window.average_latency_ms == 150.0
        assert window.by_model_provider == {"ollama": 2, "anthropic": 1}

    async def test_averages_are_none_when_nothing_reported_them(
        self, statistics_service, executions_repo, make_agent, organization_id
    ) -> None:
        agent = await make_agent(slug="unpriced")
        await _execution(executions_repo, agent, cost_usd=0.0, latency_ms=None)

        window = await statistics_service.rollup(
            organization_id, window_start=ago(3600), window_end=soon(3600)
        )

        assert window.average_cost_usd is None
        assert window.average_latency_ms is None

    async def test_counts_tool_usage_from_execution_traces(
        self, statistics_service, executions_repo, make_agent, organization_id
    ) -> None:
        agent = await make_agent(slug="tooled")
        await _execution(
            executions_repo,
            agent,
            trace=[
                {"type": "tool_call", "tool_key": "probe"},
                {"type": "tool_call", "tool_key": "probe"},
                {"type": "tool_call", "tool_key": "lookup"},
                {"type": "tool_call"},
                {"type": "final", "tool_key": "ignored"},
            ],
        )

        window = await statistics_service.rollup(
            organization_id, window_start=ago(3600), window_end=soon(3600)
        )

        assert window.by_tool == {"probe": 2, "lookup": 1}

    async def test_counts_memory_rows_created_in_the_window(
        self, statistics_service, memory_service, make_agent, organization_id
    ) -> None:
        agent = await make_agent(slug="remembering")
        for key in ("one", "two"):
            await memory_service.remember(
                agent_id=agent.id,
                organization_id=organization_id,
                project_id=None,
                scope=MemoryScope.LONG_TERM,
                key=key,
                content={"value": key},
            )

        window = await statistics_service.rollup(
            organization_id, window_start=ago(3600), window_end=soon(3600)
        )

        assert window.memory_rows_created == 2

    async def test_is_scoped_to_one_organization(
        self, statistics_service, agent_service, executions_repo, make_agent, organization_id
    ) -> None:
        other_org = uuid.uuid4()
        other_agent = await agent_service.register(
            organization_id=other_org,
            slug="theirs",
            name="Theirs",
            agent_type=AgentType.EXECUTOR,
            profile=ProfileFields(),
        )
        await _execution(executions_repo, other_agent, total_tokens=999)
        await make_agent(slug="ours")

        window = await statistics_service.rollup(
            organization_id, window_start=ago(3600), window_end=soon(3600)
        )

        assert window.active_agents == 1
        assert window.total_tokens == 0

    async def test_stored_window_is_the_latest(
        self, statistics_service, statistics_repo, organization_id
    ) -> None:
        start, end = ago(3600), soon(3600)

        window = await statistics_service.rollup(
            organization_id, window_start=start, window_end=end
        )

        latest = await statistics_repo.latest(organization_id)

        assert latest is not None
        assert latest.id == window.id
        assert latest.window_start == start
        assert latest.window_end == end


# ---------------------------------------------------------------------------
# StatisticsService.dashboard / trend
# ---------------------------------------------------------------------------


class TestDashboardAndTrend:
    async def test_dashboard_is_all_none_before_any_rollup(
        self, statistics_service, organization_id
    ) -> None:
        assert await statistics_service.dashboard(organization_id) == {
            "latest_window": {
                "active_agents": None,
                "task_count": None,
                "executions_succeeded": None,
                "executions_failed": None,
                "average_latency_ms": None,
                "computed_through": None,
            }
        }

    async def test_dashboard_reports_the_latest_window(
        self, statistics_service, executions_repo, task_service, make_agent, organization_id
    ) -> None:
        agent = await make_agent(slug="dashboarded")
        await task_service.create_task(
            organization_id=organization_id, task_type="analysis", payload={}
        )
        await _execution(executions_repo, agent, latency_ms=40.0)
        await _execution(executions_repo, agent, status=ExecutionStatus.FAILED)
        end = soon(3600)
        await statistics_service.rollup(organization_id, window_start=ago(3600), window_end=end)

        dashboard = await statistics_service.dashboard(organization_id)

        assert dashboard["latest_window"] == {
            "active_agents": 1,
            "task_count": 1,
            "executions_succeeded": 1,
            "executions_failed": 1,
            "average_latency_ms": 40.0,
            "computed_through": end.isoformat(),
        }

    async def test_trend_returns_windows_oldest_first(
        self, statistics_service, organization_id
    ) -> None:
        older = await statistics_service.rollup(
            organization_id, window_start=ago(7200), window_end=ago(3600)
        )
        newer = await statistics_service.rollup(
            organization_id, window_start=ago(3600), window_end=utcnow()
        )

        trend = await statistics_service.trend(organization_id)

        assert [window.id for window in trend] == [older.id, newer.id]

    async def test_trend_excludes_windows_older_than_the_cutoff(
        self, statistics_service, organization_id
    ) -> None:
        await statistics_service.rollup(
            organization_id, window_start=ago(86_400 * 5), window_end=ago(86_400 * 5 - 60)
        )
        recent = await statistics_service.rollup(
            organization_id, window_start=ago(600), window_end=utcnow()
        )

        trend = await statistics_service.trend(organization_id, since_days=1)

        assert [window.id for window in trend] == [recent.id]

    async def test_trend_is_empty_for_a_quiet_organization(
        self, statistics_service, organization_id
    ) -> None:
        assert await statistics_service.trend(organization_id) == []


# ---------------------------------------------------------------------------
# ReportService.generate
# ---------------------------------------------------------------------------


class TestGenerate:
    async def test_usage_report_rows(
        self, report_service, agents_repo, make_agent, organization_id
    ) -> None:
        agent = await make_agent(slug="used", agent_type=AgentType.MONITORING)
        agent.consecutive_failures = 2
        executed_at = ago(60)
        agent.last_executed_at = executed_at
        await agents_repo.update(agent)

        report = await report_service.generate(organization_id, kind=ReportKind.USAGE)

        assert report.status == ReportStatus.COMPLETED
        assert report.content["rows"] == [
            {
                "slug": "used",
                "agent_type": "monitoring",
                "status": "active",
                "consecutive_failures": 2,
                "last_executed_at": executed_at.isoformat(),
            }
        ]
        assert report.row_count == 1

    async def test_usage_report_leaves_a_never_run_agent_null(
        self, report_service, make_agent, organization_id
    ) -> None:
        await make_agent(slug="never-run")

        report = await report_service.generate(organization_id, kind=ReportKind.USAGE)

        assert report.content["rows"][0]["last_executed_at"] is None

    async def test_execution_report_rows(
        self, report_service, executions_repo, make_agent, organization_id
    ) -> None:
        agent = await make_agent(slug="executed")
        started = ago(120)
        await _execution(
            executions_repo,
            agent,
            total_tokens=42,
            cost_usd=0.25,
            latency_ms=310.5,
            started_at=started,
        )

        report = await report_service.generate(organization_id, kind=ReportKind.EXECUTION)

        assert report.status == ReportStatus.COMPLETED
        assert report.content["rows"] == [
            {
                "agent_slug": "executed",
                "status": "completed",
                "total_tokens": 42,
                "cost_usd": 0.25,
                "latency_ms": 310.5,
                "started_at": started.isoformat(),
            }
        ]

    async def test_execution_report_spans_every_agent_newest_first(
        self, report_service, executions_repo, make_agent, organization_id
    ) -> None:
        first = await make_agent(slug="alpha")
        second = await make_agent(slug="beta")
        await _execution(executions_repo, first, started_at=ago(600))
        await _execution(executions_repo, first, started_at=ago(60))
        await _execution(executions_repo, second, started_at=ago(30))

        report = await report_service.generate(organization_id, kind=ReportKind.EXECUTION)

        assert [row["agent_slug"] for row in report.content["rows"]] == ["alpha", "alpha", "beta"]
        assert report.row_count == 3

    async def test_execution_report_respects_max_rows(
        self, reports_repo, agents_repo, executions_repo, audit_repo, make_agent, organization_id
    ) -> None:
        agent = await make_agent(slug="prolific")
        await _execution(executions_repo, agent)
        await _execution(executions_repo, agent)
        service = ReportService(reports_repo, agents_repo, executions_repo, audit_repo, max_rows=1)

        report = await service.generate(organization_id, kind=ReportKind.EXECUTION)

        assert report.row_count == 1

    async def test_audit_report_rows(self, report_service, audit_service, organization_id) -> None:
        entry = await audit_service.record(
            organization_id,
            action=AuditAction.TOOL_USED,
            entity_type="tool",
            summary="Probe was invoked.",
            actor_id="operator-1",
            succeeded=False,
        )

        report = await report_service.generate(organization_id, kind=ReportKind.AUDIT)

        assert report.status == ReportStatus.COMPLETED
        assert report.content["rows"] == [
            {
                "action": "tool_used",
                "entity_type": "tool",
                "actor_id": "operator-1",
                "occurred_at": entry.occurred_at.isoformat(),
                "succeeded": False,
            }
        ]

    async def test_audit_report_includes_registration_entries(
        self, report_service, make_agent, organization_id
    ) -> None:
        await make_agent(slug="audited")

        report = await report_service.generate(organization_id, kind=ReportKind.AUDIT)

        assert [row["action"] for row in report.content["rows"]] == ["agent_registered"]
        assert report.content["rows"][0]["entity_type"] == "agent"

    @pytest.mark.parametrize(
        "kind",
        [ReportKind.EVALUATION, ReportKind.BENCHMARK, ReportKind.COST, ReportKind.PERFORMANCE],
    )
    async def test_unbuilt_kinds_complete_with_no_rows(
        self, report_service, make_agent, kind, organization_id
    ) -> None:
        await make_agent(slug="ignored")

        report = await report_service.generate(organization_id, kind=kind)

        assert report.status == ReportStatus.COMPLETED
        assert report.content == {"rows": []}
        assert report.row_count == 0

    async def test_metadata_defaults(self, report_service, organization_id) -> None:
        before = utcnow()

        report = await report_service.generate(organization_id, kind=ReportKind.USAGE)

        assert report.title == "usage report"
        assert report.report_format == ReportFormat.JSON
        assert report.generated_by is None
        assert report.error is None
        assert report.generated_at is not None
        assert report.generated_at >= before
        assert report.duration_ms is not None
        assert report.duration_ms >= 0

    async def test_metadata_is_taken_from_the_caller(self, report_service, organization_id) -> None:
        report = await report_service.generate(
            organization_id,
            kind=ReportKind.AUDIT,
            report_format=ReportFormat.CSV,
            title="Quarterly audit",
            generated_by="operator-7",
        )

        assert report.title == "Quarterly audit"
        assert report.report_format == ReportFormat.CSV
        assert report.generated_by == "operator-7"

    async def test_a_build_failure_is_recorded_not_raised(
        self, reports_repo, unreachable_agents_repo, executions_repo, audit_repo, organization_id
    ) -> None:
        service = ReportService(reports_repo, unreachable_agents_repo, executions_repo, audit_repo)

        report = await service.generate(organization_id, kind=ReportKind.USAGE)

        assert report.status == ReportStatus.FAILED
        assert report.error
        assert report.content == {}
        assert report.row_count is None
        assert report.generated_at is None

    async def test_a_failed_report_is_still_persisted(
        self,
        reports_repo,
        unreachable_agents_repo,
        executions_repo,
        audit_repo,
        organization_id,
    ) -> None:
        service = ReportService(reports_repo, unreachable_agents_repo, executions_repo, audit_repo)

        report = await service.generate(organization_id, kind=ReportKind.EXECUTION)

        stored = await reports_repo.list_for_org(organization_id)

        assert [row.id for row in stored] == [report.id]
        assert stored[0].status == ReportStatus.FAILED


# ---------------------------------------------------------------------------
# ReportService.require_in_org / list_for_org
# ---------------------------------------------------------------------------


class TestReportLookup:
    async def test_require_in_org_returns_the_report(self, report_service, organization_id) -> None:
        report = await report_service.generate(organization_id, kind=ReportKind.USAGE)

        found = await report_service.require_in_org(organization_id, report.id)

        assert found.id == report.id

    async def test_require_in_org_rejects_another_organization(
        self, report_service, organization_id
    ) -> None:
        report = await report_service.generate(organization_id, kind=ReportKind.USAGE)

        with pytest.raises(NotFoundError):
            await report_service.require_in_org(uuid.uuid4(), report.id)

    async def test_list_for_org_returns_every_report(self, report_service, organization_id) -> None:
        usage = await report_service.generate(organization_id, kind=ReportKind.USAGE)
        audit = await report_service.generate(organization_id, kind=ReportKind.AUDIT)

        found = await report_service.list_for_org(organization_id)

        assert {row.id for row in found} == {usage.id, audit.id}

    async def test_list_for_org_filters_by_kind(self, report_service, organization_id) -> None:
        await report_service.generate(organization_id, kind=ReportKind.USAGE)
        audit = await report_service.generate(organization_id, kind=ReportKind.AUDIT)

        found = await report_service.list_for_org(organization_id, kind=ReportKind.AUDIT)

        assert [row.id for row in found] == [audit.id]

    async def test_list_for_org_is_scoped(self, report_service, organization_id) -> None:
        await report_service.generate(organization_id, kind=ReportKind.USAGE)

        assert await report_service.list_for_org(uuid.uuid4()) == []


# ---------------------------------------------------------------------------
# AuditService
# ---------------------------------------------------------------------------


class TestAuditService:
    async def test_record_defaults(self, audit_service, organization_id) -> None:
        before = utcnow()

        entry = await audit_service.record(
            organization_id,
            action=AuditAction.EXECUTED,
            entity_type="agent",
            summary="An agent ran.",
        )

        assert entry.organization_id == organization_id
        assert entry.action == AuditAction.EXECUTED
        assert entry.entity_type == "agent"
        assert entry.summary == "An agent ran."
        assert entry.actor_type == "user"
        assert entry.succeeded is True
        assert entry.changes == {}
        assert entry.context == {}
        assert entry.entity_id is None
        assert entry.entity_reference is None
        assert entry.actor_id is None
        assert entry.request_id is None
        assert entry.ip_address is None
        assert entry.occurred_at >= before

    async def test_record_persists_every_field(
        self, audit_service, audit_repo, organization_id
    ) -> None:
        entity_id = uuid.uuid4()

        entry = await audit_service.record(
            organization_id,
            action=AuditAction.PERMISSION_GRANTED,
            entity_type="permission",
            summary="Granted tool invocation.",
            entity_id=entity_id,
            entity_reference="tool_invocation",
            actor_id="operator-2",
            actor_type="service",
            succeeded=False,
            changes={"status": "granted"},
            context={"request": "abc"},
            request_id="req-1",
            ip_address="10.0.0.1",
        )

        stored = await audit_repo.list_for_entity("permission", entity_id)

        assert [row.id for row in stored] == [entry.id]
        assert stored[0].entity_reference == "tool_invocation"
        assert stored[0].actor_id == "operator-2"
        assert stored[0].actor_type == "service"
        assert stored[0].succeeded is False
        assert stored[0].changes == {"status": "granted"}
        assert stored[0].context == {"request": "abc"}
        assert stored[0].request_id == "req-1"
        assert stored[0].ip_address == "10.0.0.1"

    async def test_list_entries_is_newest_first(self, audit_service, organization_id) -> None:
        first = await audit_service.record(
            organization_id,
            action=AuditAction.EXECUTED,
            entity_type="agent",
            summary="First.",
        )
        second = await audit_service.record(
            organization_id,
            action=AuditAction.TOOL_USED,
            entity_type="tool",
            summary="Second.",
        )

        entries = await audit_service.list_entries(organization_id)

        assert [entry.id for entry in entries] == [second.id, first.id]

    async def test_list_entries_respects_the_limit(self, audit_service, organization_id) -> None:
        for index in range(3):
            await audit_service.record(
                organization_id,
                action=AuditAction.EXECUTED,
                entity_type="agent",
                summary=f"Entry {index}.",
            )

        assert len(await audit_service.list_entries(organization_id, limit=2)) == 2

    async def test_list_entries_is_scoped(self, audit_service, organization_id) -> None:
        await audit_service.record(
            organization_id,
            action=AuditAction.EXECUTED,
            entity_type="agent",
            summary="Ours.",
        )

        assert await audit_service.list_entries(uuid.uuid4()) == []

    async def test_summary_counts_each_action(
        self, audit_service, make_agent, organization_id
    ) -> None:
        await make_agent(slug="summarised")
        await audit_service.record(
            organization_id,
            action=AuditAction.TOOL_USED,
            entity_type="tool",
            summary="One.",
        )
        await audit_service.record(
            organization_id,
            action=AuditAction.TOOL_USED,
            entity_type="tool",
            summary="Two.",
        )

        summary = await audit_service.summary(organization_id)

        assert summary["by_action"] == {"agent_registered": 1, "tool_used": 2}
        assert summary["total"] == 3
        assert summary["since"].endswith("+00:00")

    async def test_summary_is_empty_for_a_quiet_organization(
        self, audit_service, organization_id
    ) -> None:
        summary = await audit_service.summary(organization_id)

        assert summary["by_action"] == {}
        assert summary["total"] == 0

    async def test_summary_window_excludes_older_entries(
        self, audit_service, audit_repo, organization_id
    ) -> None:
        old = await audit_service.record(
            organization_id,
            action=AuditAction.EXECUTED,
            entity_type="agent",
            summary="Ancient.",
        )
        old.occurred_at = ago(86_400 * 40)
        await audit_repo.update(old)

        summary = await audit_service.summary(organization_id, days=30)

        assert summary["by_action"] == {}
        assert summary["total"] == 0
