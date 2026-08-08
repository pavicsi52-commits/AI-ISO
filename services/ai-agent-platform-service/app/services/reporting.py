"""Statistics rollup, generated reports, and the append-only audit
trail (docs/060 "OBSERVABILITY", "GOVERNANCE"; backs ``GET
/agents/statistics``, ``GET /agents/reports``).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar
from uuid import UUID

from shared_core.logging.logger import get_logger

from app.models.enums import (
    AgentLifecycleStatus,
    AuditAction,
    ReportFormat,
    ReportKind,
    ReportStatus,
)
from app.models.governance import AgentAudit, AgentReport, AgentStatistic
from app.repositories.agent import AgentRepository
from app.repositories.execution import AgentExecutionRepository
from app.repositories.governance import (
    AgentAuditRepository,
    AgentReportRepository,
    AgentStatisticRepository,
)
from app.repositories.memory import AgentMemoryRepository
from app.repositories.task import AgentTaskRepository

logger = get_logger("app.services.reporting")


class StatisticsService:
    """Rolls agent activity up into windows, for trending and dashboards."""

    def __init__(
        self,
        statistics: AgentStatisticRepository,
        agents: AgentRepository,
        tasks: AgentTaskRepository,
        executions: AgentExecutionRepository,
        memory: AgentMemoryRepository,
    ) -> None:
        self._statistics = statistics
        self._agents = agents
        self._tasks = tasks
        self._executions = executions
        self._memory = memory

    async def rollup(
        self, organization_id: UUID, *, window_start: datetime, window_end: datetime
    ) -> AgentStatistic:
        """Compute and store one window's statistics."""
        agents = await self._agents.list_for_org(organization_id)
        active_agents = sum(1 for agent in agents if agent.status == AgentLifecycleStatus.ACTIVE)
        by_agent_type: dict[str, int] = {}
        for agent in agents:
            key = str(agent.agent_type)
            by_agent_type[key] = by_agent_type.get(key, 0) + 1

        tasks = await self._tasks.list_in_window(
            organization_id, since=window_start, until=window_end
        )
        executions = await self._executions.list_in_window(
            organization_id, since=window_start, until=window_end
        )
        succeeded = sum(1 for execution in executions if str(execution.status) == "completed")
        failed = sum(1 for execution in executions if str(execution.status) == "failed")
        total_tokens = sum(execution.total_tokens for execution in executions)
        costs = [execution.cost_usd for execution in executions if execution.cost_usd]
        latencies = [execution.latency_ms for execution in executions if execution.latency_ms]

        by_model_provider: dict[str, int] = {}
        by_tool: dict[str, int] = {}
        for execution in executions:
            provider_key = str(execution.model_provider)
            by_model_provider[provider_key] = by_model_provider.get(provider_key, 0) + 1
            for entry in execution.trace:
                if entry.get("type") == "tool_call" and entry.get("tool_key"):
                    tool_key = str(entry["tool_key"])
                    by_tool[tool_key] = by_tool.get(tool_key, 0) + 1

        memory_rows_created = await self._memory.count_created_in_window(
            organization_id, since=window_start, until=window_end
        )

        window = AgentStatistic(
            organization_id=organization_id,
            window_start=window_start,
            window_end=window_end,
            active_agents=active_agents,
            task_count=len(tasks),
            executions_succeeded=succeeded,
            executions_failed=failed,
            total_tokens=total_tokens,
            average_cost_usd=(sum(costs) / len(costs)) if costs else None,
            average_latency_ms=(sum(latencies) / len(latencies)) if latencies else None,
            memory_rows_created=memory_rows_created,
            by_agent_type=by_agent_type,
            by_model_provider=by_model_provider,
            by_tool=by_tool,
        )
        return await self._statistics.create(window)

    async def dashboard(self, organization_id: UUID) -> dict[str, Any]:
        """The live snapshot a dashboard reads on load."""
        latest = await self._statistics.latest(organization_id)
        return {
            "latest_window": {
                "active_agents": latest.active_agents if latest else None,
                "task_count": latest.task_count if latest else None,
                "executions_succeeded": latest.executions_succeeded if latest else None,
                "executions_failed": latest.executions_failed if latest else None,
                "average_latency_ms": latest.average_latency_ms if latest else None,
                "computed_through": latest.window_end.isoformat() if latest else None,
            }
        }

    async def trend(self, organization_id: UUID, *, since_days: int = 30) -> list[AgentStatistic]:
        """Recent windows, oldest first, for a trend chart."""
        since = datetime.now(UTC) - timedelta(days=since_days)
        return await self._statistics.list_since(organization_id, since=since)


class ReportService:
    """Generates the documents docs/060's own "REPORTING" section asks for.

    Only ``EXECUTION``/``USAGE``/``AUDIT`` have real builders;
    ``EVALUATION``/``BENCHMARK``/``COST``/``PERFORMANCE`` return empty
    rows -- the same "not every report kind needs a bespoke builder in
    the first cut" scope decision established across every prior
    AI-IOS service's own ``ReportService``.
    """

    def __init__(
        self,
        reports: AgentReportRepository,
        agents: AgentRepository,
        executions: AgentExecutionRepository,
        audits: AgentAuditRepository,
        *,
        max_rows: int = 10_000,
    ) -> None:
        self._reports = reports
        self._agents = agents
        self._executions = executions
        self._audits = audits
        self._max_rows = max_rows

    async def generate(
        self,
        organization_id: UUID,
        *,
        kind: ReportKind,
        report_format: ReportFormat = ReportFormat.JSON,
        title: str | None = None,
        generated_by: str | None = None,
    ) -> AgentReport:
        """Build and store one report.

        A failure to build never raises to the caller -- it is
        recorded on the row instead, as ``FAILED`` with an ``error``.
        """
        started = datetime.now(UTC)
        record = await self._reports.create(
            AgentReport(
                organization_id=organization_id,
                kind=kind,
                report_format=report_format,
                title=title or f"{kind!s} report",
                status=ReportStatus.RUNNING,
                generated_by=generated_by,
            )
        )
        try:
            content = await self._build(organization_id, kind)
        except Exception as exc:
            record.status = ReportStatus.FAILED
            record.error = str(exc)
            logger.warning(
                "Could not build a report.",
                extra={"extra_fields": {"kind": str(kind), "error": str(exc)}},
            )
            return await self._reports.update(record)

        record.status = ReportStatus.COMPLETED
        record.content = content
        record.row_count = len(content.get("rows", []))
        record.generated_at = datetime.now(UTC)
        record.duration_ms = (record.generated_at - started).total_seconds() * 1_000
        return await self._reports.update(record)

    async def _build(self, organization_id: UUID, kind: ReportKind) -> dict[str, Any]:
        builder = self._BUILDERS.get(kind)
        return await builder(self, organization_id) if builder else {"rows": []}

    async def _build_usage(self, organization_id: UUID) -> dict[str, Any]:
        agents = await self._agents.list_for_org(organization_id)
        return {
            "rows": [
                {
                    "slug": agent.slug,
                    "agent_type": str(agent.agent_type),
                    "status": str(agent.status),
                    "consecutive_failures": agent.consecutive_failures,
                    "last_executed_at": (
                        agent.last_executed_at.isoformat() if agent.last_executed_at else None
                    ),
                }
                for agent in agents
            ]
        }

    async def _build_execution(self, organization_id: UUID) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        agents = await self._agents.list_for_org(organization_id)
        for agent in agents:
            executions = await self._executions.list_for_agent(agent.id, limit=self._max_rows)
            rows.extend(
                {
                    "agent_slug": agent.slug,
                    "status": str(execution.status),
                    "total_tokens": execution.total_tokens,
                    "cost_usd": execution.cost_usd,
                    "latency_ms": execution.latency_ms,
                    "started_at": execution.started_at.isoformat(),
                }
                for execution in executions
            )
        return {"rows": rows[: self._max_rows]}

    async def _build_audit(self, organization_id: UUID) -> dict[str, Any]:
        rows = await self._audits.list_for_org(organization_id, limit=self._max_rows)
        return {
            "rows": [
                {
                    "action": str(row.action),
                    "entity_type": row.entity_type,
                    "actor_id": row.actor_id,
                    "occurred_at": row.occurred_at.isoformat(),
                    "succeeded": row.succeeded,
                }
                for row in rows
            ]
        }

    _BUILDERS: ClassVar[dict[ReportKind, Any]] = {
        ReportKind.USAGE: _build_usage,
        ReportKind.EXECUTION: _build_execution,
        ReportKind.AUDIT: _build_audit,
    }

    async def require_in_org(self, organization_id: UUID, report_id: UUID) -> AgentReport:
        """One report.

        Raises:
            NotFoundError: If it does not exist here.
        """
        return await self._reports.require_in_org(organization_id, report_id)

    async def list_for_org(
        self, organization_id: UUID, *, kind: ReportKind | None = None
    ) -> list[AgentReport]:
        """Reports, newest first."""
        return await self._reports.list_for_org(organization_id, kind=kind)


class AuditService:
    """Writes and reads the append-only agent-platform audit trail."""

    def __init__(self, audits: AgentAuditRepository) -> None:
        self._audits = audits

    async def record(
        self,
        organization_id: UUID,
        *,
        action: AuditAction,
        entity_type: str,
        summary: str,
        entity_id: UUID | None = None,
        entity_reference: str | None = None,
        actor_id: str | None = None,
        actor_type: str = "user",
        succeeded: bool = True,
        changes: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
        request_id: str | None = None,
        ip_address: str | None = None,
    ) -> AgentAudit:
        """Append one entry."""
        return await self._audits.create(
            AgentAudit(
                organization_id=organization_id,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                entity_reference=entity_reference,
                actor_id=actor_id,
                actor_type=actor_type,
                occurred_at=datetime.now(UTC),
                summary=summary,
                succeeded=succeeded,
                changes=dict(changes or {}),
                context=dict(context or {}),
                request_id=request_id,
                ip_address=ip_address,
            )
        )

    async def list_entries(self, organization_id: UUID, *, limit: int = 200) -> list[AgentAudit]:
        """Audit entries, newest first."""
        return await self._audits.list_for_org(organization_id, limit=limit)

    async def summary(self, organization_id: UUID, *, days: int = 30) -> dict[str, Any]:
        """How much of each action has happened lately."""
        since = datetime.now(UTC) - timedelta(days=days)
        counts = await self._audits.count_by_action(organization_id, since=since)
        return {"since": since.isoformat(), "total": sum(counts.values()), "by_action": counts}


__all__ = ["AuditService", "ReportService", "StatisticsService"]
