"""Analytics, statistics rollup, reporting, and the audit trail."""

from __future__ import annotations

import csv
import io
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from shared_core.database.session import session_scope
from shared_core.logging.logger import get_logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.enums import (
    AssessmentStatus,
    AuditAction,
    JobStatus,
    RemediationStatus,
    ReportFormat,
    ReportKind,
    ScoreScope,
)
from app.models.governance import ComplianceAudit, ComplianceReport, ComplianceStatistic
from app.repositories.catalogue import ControlRepository, FrameworkRepository
from app.repositories.governance import (
    AuditRepository,
    ExceptionRepository,
    FindingRepository,
    RemediationRepository,
    ReportRepository,
    RiskRepository,
    ScoreRepository,
    StatisticRepository,
)
from app.repositories.runs import (
    AssessmentRepository,
    EvidenceRepository,
    ResultRepository,
    ScanRepository,
)
from app.services.evidence import EvidenceService

logger = get_logger("app.services.reporting")


class StatisticsService:
    """Rolls activity up into windows, for trending."""

    def __init__(
        self,
        statistics: StatisticRepository,
        assessments: AssessmentRepository,
        scans: ScanRepository,
        results: ResultRepository,
        evidence: EvidenceRepository,
        findings: FindingRepository,
        risks: RiskRepository,
        exceptions: ExceptionRepository,
        remediations: RemediationRepository,
        scores: ScoreRepository,
        controls: ControlRepository,
        frameworks: FrameworkRepository,
    ) -> None:
        self._statistics = statistics
        self._assessments = assessments
        self._scans = scans
        self._results = results
        self._evidence = evidence
        self._findings = findings
        self._risks = risks
        self._exceptions = exceptions
        self._remediations = remediations
        self._scores = scores
        self._controls = controls
        self._frameworks = frameworks

    async def rollup(
        self,
        organization_id: UUID,
        *,
        window_start: datetime,
        window_end: datetime,
        actor_id: UUID | None = None,
    ) -> ComplianceStatistic:
        """Compute one window's statistics.

        **Idempotent by window start.** A scheduled rollup that runs
        twice -- after a retry, a redeploy, or a leader election -- must
        not double every number in the trend. Overwriting the existing
        row is right because the window's contents are derived, so
        recomputing gives the same answer plus anything that arrived
        late.
        """
        assessments = await self._assessments.count_in_window(
            organization_id, since=window_start, until=window_end
        )
        remediations = await self._remediations.count_in_window(
            organization_id, since=window_start, until=window_end
        )
        completed = remediations.get(str(RemediationStatus.COMPLETED), 0)
        verified = remediations.get(str(RemediationStatus.VERIFIED), 0)
        attempted = sum(remediations.values())

        opened = await self._findings.count_in_window(
            organization_id, since=window_start, until=window_end
        )
        resolved = await self._findings.count_in_window(
            organization_id, since=window_start, until=window_end, resolved=True
        )
        by_severity = await self._findings.count_by_severity(organization_id, open_only=True)

        latest = await self._scores.latest(organization_id, scope=ScoreScope.OVERALL)
        implementation = await self._controls.count_by_status(organization_id)
        frameworks = await self._frameworks.list_active(organization_id)

        expiring = await self._exceptions.list_expiring(
            organization_id, before=datetime.now(UTC) + timedelta(days=14)
        )

        existing = await self._statistics.get_window(organization_id, window_start=window_start)
        record = existing or ComplianceStatistic(
            organization_id=organization_id,
            window_start=window_start,
            window_end=window_end,
            created_by=actor_id,
        )

        record.window_end = window_end
        record.assessments_run = sum(assessments.values())
        record.assessments_failed = assessments.get(str(AssessmentStatus.FAILED), 0)
        record.scans_run = await self._scans.count_in_window(
            organization_id, since=window_start, until=window_end
        )
        record.controls_evaluated = await self._results.count_in_window(
            organization_id, since=window_start, until=window_end
        )
        record.evidence_collected = await self._evidence.count_in_window(
            organization_id, since=window_start, until=window_end
        )
        record.findings_opened = opened
        record.findings_resolved = resolved
        record.findings_open_total = await self._findings.count_open(organization_id)
        record.findings_critical = by_severity.get("critical", 0)
        record.risks_registered = await self._risks.count_in_window(
            organization_id, since=window_start, until=window_end
        )
        record.risks_open_total = await self._risks.count_open(organization_id)
        record.exceptions_active = await self._exceptions.count_active(organization_id)
        record.exceptions_expiring = len(expiring)
        record.remediations_completed = completed
        record.remediations_verified = verified
        # Verified over attempted, not completed over attempted. "We ran
        # the fix" is not "the control passes", and a success rate built
        # on the first number reports a programme as working when it may
        # only be busy.
        record.remediation_success_rate = (
            round(verified / attempted * 100.0, 2) if attempted else 0.0
        )
        record.average_score = latest.score if latest is not None else 0.0
        record.framework_coverage = float(len(frameworks))
        total_controls = sum(implementation.values())
        record.control_coverage = (
            round(
                implementation.get("implemented", 0) / total_controls * 100.0,
                2,
            )
            if total_controls
            else 0.0
        )
        record.breakdown = {
            "assessments_by_status": assessments,
            "remediations_by_status": remediations,
            "findings_by_severity": by_severity,
            "controls_by_status": implementation,
        }
        record.updated_by = actor_id

        return record if existing else await self._statistics.create(record)

    async def recent(self, organization_id: UUID, *, limit: int = 30) -> list[ComplianceStatistic]:
        """Recent windows, newest first."""
        return await self._statistics.list_recent(organization_id, limit=limit)

    async def dashboard(self, organization_id: UUID) -> dict[str, Any]:
        """Everything a compliance dashboard needs, in one call."""
        latest_score = await self._scores.latest(organization_id, scope=ScoreScope.OVERALL)
        by_severity = await self._findings.count_by_severity(organization_id, open_only=True)
        now = datetime.now(UTC)
        return {
            "score": latest_score.score if latest_score else None,
            "grade": str(latest_score.grade) if latest_score else None,
            "delta": latest_score.delta if latest_score else None,
            "coverage": (latest_score.breakdown or {}).get("coverage") if latest_score else None,
            "findings_open": await self._findings.count_open(organization_id),
            "findings_by_severity": by_severity,
            "findings_overdue": len(
                await self._findings.list_overdue(organization_id, now=now, limit=1_000)
            ),
            "risks_open": await self._risks.count_open(organization_id),
            "exceptions_active": await self._exceptions.count_active(organization_id),
            "exceptions_expiring": len(
                await self._exceptions.list_expiring(
                    organization_id, before=now + timedelta(days=14)
                )
            ),
            "frameworks_active": len(await self._frameworks.list_active(organization_id)),
            "controls_by_status": await self._controls.count_by_status(organization_id),
        }


ReportBuilder = Callable[[UUID, dict[str, Any]], Awaitable[dict[str, Any]]]


class ReportService:
    """Generates the documents an audit actually asks for."""

    def __init__(
        self,
        reports: ReportRepository,
        statistics: StatisticsService,
        findings: FindingRepository,
        risks: RiskRepository,
        exceptions: ExceptionRepository,
        controls: ControlRepository,
        frameworks: FrameworkRepository,
        evidence: EvidenceRepository,
        assessments: AssessmentRepository,
        results: ResultRepository,
        scores: ScoreRepository,
        audits: AuditRepository,
        *,
        max_rows: int = 10_000,
    ) -> None:
        self._reports = reports
        self._statistics = statistics
        self._findings = findings
        self._risks = risks
        self._exceptions = exceptions
        self._controls = controls
        self._frameworks = frameworks
        self._evidence = evidence
        self._assessments = assessments
        self._results = results
        self._scores = scores
        self._audits = audits
        self._max_rows = max_rows

    async def generate(
        self,
        organization_id: UUID,
        *,
        kind: ReportKind,
        report_format: ReportFormat = ReportFormat.JSON,
        title: str | None = None,
        framework_id: UUID | None = None,
        assessment_id: UUID | None = None,
        period_days: int = 90,
        actor_id: UUID | None = None,
    ) -> ComplianceReport:
        """Build a report and store it.

        A failure is recorded on the report row rather than raised past
        the caller: somebody who asked for a report needs to be told what
        went wrong with it, and a stack trace in a log they cannot see is
        not that.
        """
        started = time.perf_counter()
        now = datetime.now(UTC)
        record = await self._reports.create(
            ComplianceReport(
                organization_id=organization_id,
                kind=kind,
                report_format=report_format,
                title=title or f"{str(kind).replace('_', ' ').title()} report",
                status=JobStatus.RUNNING,
                framework_id=framework_id,
                assessment_id=assessment_id,
                period_start=now - timedelta(days=period_days),
                period_end=now,
                generated_by=str(actor_id) if actor_id else None,
                created_by=actor_id,
            )
        )

        try:
            content = await self._build(
                organization_id,
                kind=kind,
                framework_id=framework_id,
                assessment_id=assessment_id,
                period_days=period_days,
            )
        except Exception as exc:
            record.status = JobStatus.FAILED
            record.error = str(exc)
            record.duration_ms = (time.perf_counter() - started) * 1_000
            logger.exception(
                "A compliance report could not be generated.",
                extra={
                    "extra_fields": {
                        "organization_id": str(organization_id),
                        "kind": str(kind),
                    }
                },
            )
            return await self._reports.update(record)

        record.content = content
        record.row_count = len(content.get("rows", []))
        record.status = JobStatus.COMPLETED
        record.generated_at = datetime.now(UTC)
        record.duration_ms = (time.perf_counter() - started) * 1_000
        return await self._reports.update(record)

    async def _build(
        self,
        organization_id: UUID,
        *,
        kind: ReportKind,
        framework_id: UUID | None,
        assessment_id: UUID | None,
        period_days: int,
    ) -> dict[str, Any]:
        """Dispatch to the right builder.

        Raises:
            ValueError: If the kind has no builder. Loud rather than an
                empty report, because an empty compliance report reads as
                "nothing to report", which is the opposite of "I could
                not tell you".
        """
        builders = {
            ReportKind.EXECUTIVE: self._executive,
            ReportKind.FRAMEWORK: self._framework,
            ReportKind.ASSESSMENT: self._assessment,
            ReportKind.EVIDENCE: self._evidence_report,
            ReportKind.RISK: self._risk,
            ReportKind.CONTROL: self._control,
            ReportKind.EXCEPTION: self._exception,
            ReportKind.AUDIT: self._audit,
            ReportKind.TREND: self._trend,
        }
        builder = builders.get(kind)
        if builder is None:
            raise ValueError(f"No builder for report kind {str(kind)!r}.")
        return await builder(
            organization_id,
            {
                "framework_id": framework_id,
                "assessment_id": assessment_id,
                "period_days": period_days,
            },
        )

    async def _executive(self, organization_id: UUID, params: dict[str, Any]) -> dict[str, Any]:
        """The one-page summary, with coverage beside the score."""
        dashboard = await self._statistics.dashboard(organization_id)
        return {
            "summary": dashboard,
            "narrative": (
                f"Compliance score {dashboard['score']}% "
                f"({dashboard['grade']}) across {dashboard['coverage']}% of in-scope "
                f"controls, with {dashboard['findings_open']} open finding(s), "
                f"{dashboard['findings_overdue']} overdue, and "
                f"{dashboard['exceptions_active']} active exception(s)."
                if dashboard["score"] is not None
                else (
                    "No compliance score has been computed yet. Run an assessment "
                    "before relying on this report."
                )
            ),
            "rows": [],
        }

    async def _framework(self, organization_id: UUID, params: dict[str, Any]) -> dict[str, Any]:
        """Per-framework posture."""
        rows = []
        for framework in await self._frameworks.list_for_org(organization_id, limit=200):
            score = await self._scores.latest(
                organization_id, scope=ScoreScope.FRAMEWORK, scope_id=str(framework.id)
            )
            rows.append(
                {
                    "framework": framework.name,
                    "code": str(framework.code),
                    "status": str(framework.status),
                    "controls": framework.control_count,
                    "score": score.score if score else None,
                    "grade": str(score.grade) if score else None,
                    "computed_at": score.computed_at.isoformat() if score else None,
                }
            )
        return {"rows": rows, "count": len(rows)}

    async def _assessment(self, organization_id: UUID, params: dict[str, Any]) -> dict[str, Any]:
        """One run in detail, or the recent runs if none is named."""
        assessment_id = params.get("assessment_id")
        if assessment_id is None:
            rows = [
                {
                    "assessment": one.name,
                    "status": str(one.status),
                    "score": one.score,
                    "passed": one.controls_passed,
                    "failed": one.controls_failed,
                    "not_assessed": one.controls_not_assessed,
                    "completed_at": one.completed_at.isoformat() if one.completed_at else None,
                }
                for one in await self._assessments.list_for_org(organization_id, limit=100)
            ]
            return {"rows": rows, "count": len(rows)}

        assessment = await self._assessments.require_in_org(organization_id, assessment_id)
        counts = await self._results.count_for_assessment(organization_id, assessment_id)
        results = await self._results.list_for_assessment(
            organization_id, assessment_id, limit=self._max_rows
        )
        return {
            "assessment": {
                "name": assessment.name,
                "status": str(assessment.status),
                "score": assessment.score,
                "summary": assessment.summary,
            },
            "counts": counts,
            "rows": [
                {
                    "control_id": str(one.control_id),
                    "target": one.target_name or one.target_id,
                    "status": str(one.status),
                    "reason": one.reason,
                }
                for one in results
            ],
            "count": len(results),
        }

    async def _evidence_report(
        self, organization_id: UUID, params: dict[str, Any]
    ) -> dict[str, Any]:
        """What proof exists, and whether it is still intact and current.

        Reports the digest and the verification outcome rather than the
        payload. An evidence report is read by people who are not
        entitled to the configuration detail inside it, and the digest is
        what makes the claim checkable without disclosing it.
        """
        rows = await self._evidence.list_for_org(organization_id, limit=self._max_rows)
        now = datetime.now(UTC)
        return {
            "rows": [
                {
                    "evidence_id": str(one.id),
                    "title": one.title,
                    "kind": str(one.kind),
                    "source": str(one.source),
                    "target_id": one.target_id,
                    "collected_at": one.collected_at.isoformat(),
                    "expires_at": one.expires_at.isoformat() if one.expires_at else None,
                    "digest": one.digest,
                    "intact": EvidenceService.verify(one),
                    "current": EvidenceService.is_current(one, now=now),
                }
                for one in rows
            ],
            "count": len(rows),
        }

    async def _risk(self, organization_id: UUID, params: dict[str, Any]) -> dict[str, Any]:
        """The register, worst first."""
        rows = await self._risks.list_filtered(organization_id, limit=self._max_rows)
        return {
            "rows": [
                {
                    "reference": one.reference,
                    "title": one.title,
                    "category": str(one.category),
                    "likelihood": str(one.likelihood),
                    "impact": str(one.impact),
                    "severity": str(one.severity),
                    "inherent_score": one.inherent_score,
                    "residual_severity": (
                        str(one.residual_severity) if one.residual_severity else None
                    ),
                    "status": str(one.status),
                    "owner": one.owner_id,
                    "next_review_at": (
                        one.next_review_at.isoformat() if one.next_review_at else None
                    ),
                }
                for one in rows
            ],
            "count": len(rows),
        }

    async def _control(self, organization_id: UUID, params: dict[str, Any]) -> dict[str, Any]:
        """Every control and where it stands."""
        rows = await self._controls.list_filtered(
            organization_id, framework_id=params.get("framework_id"), limit=self._max_rows
        )
        return {
            "rows": [
                {
                    "code": one.code,
                    "title": one.title,
                    "category": str(one.category),
                    "severity": str(one.severity),
                    "status": str(one.status),
                    "automatable": one.is_automatable,
                    "owner": one.owner_id,
                }
                for one in rows
            ],
            "count": len(rows),
        }

    async def _exception(self, organization_id: UUID, params: dict[str, Any]) -> dict[str, Any]:
        """Every waiver, with how often it has been relied on."""
        rows = await self._exceptions.list_filtered(organization_id, limit=self._max_rows)
        return {
            "rows": [
                {
                    "title": one.title,
                    "kind": str(one.kind),
                    "status": str(one.status),
                    "justification": one.business_justification,
                    "expires_at": one.expires_at.isoformat() if one.expires_at else None,
                    "next_review_at": (
                        one.next_review_at.isoformat() if one.next_review_at else None
                    ),
                    "use_count": one.use_count,
                    "approved_by": one.approved_by,
                }
                for one in rows
            ],
            "count": len(rows),
        }

    async def _audit(self, organization_id: UUID, params: dict[str, Any]) -> dict[str, Any]:
        """Who did what."""
        since = datetime.now(UTC) - timedelta(days=int(params.get("period_days") or 90))
        rows = await self._audits.list_for_org(organization_id, since=since, limit=self._max_rows)
        return {
            "rows": [
                {
                    "occurred_at": one.occurred_at.isoformat(),
                    "action": str(one.action),
                    "entity_type": one.entity_type,
                    "entity_reference": one.entity_reference,
                    "actor": one.actor_id,
                    "summary": one.summary,
                    "succeeded": one.succeeded,
                }
                for one in rows
            ],
            "count": len(rows),
        }

    async def _trend(self, organization_id: UUID, params: dict[str, Any]) -> dict[str, Any]:
        """How posture has moved."""
        windows = await self._statistics.recent(organization_id, limit=90)
        return {
            "rows": [
                {
                    "window_start": one.window_start.isoformat(),
                    "average_score": one.average_score,
                    "findings_opened": one.findings_opened,
                    "findings_resolved": one.findings_resolved,
                    "findings_open_total": one.findings_open_total,
                    "remediation_success_rate": one.remediation_success_rate,
                }
                for one in reversed(windows)
            ],
            "count": len(windows),
        }

    async def get(self, organization_id: UUID, report_id: UUID) -> ComplianceReport:
        """One report.

        Raises:
            NotFoundError: If it does not exist here.
        """
        return await self._reports.require_in_org(organization_id, report_id)

    async def list_reports(
        self, organization_id: UUID, *, limit: int = 100, offset: int = 0
    ) -> list[ComplianceReport]:
        """Reports, newest first."""
        return await self._reports.list_for_org(organization_id, limit=limit, offset=offset)

    @staticmethod
    def to_csv(content: dict[str, Any]) -> str:
        """Render a report's rows as CSV.

        Returns an empty string for a report with no rows rather than a
        bare header, so a caller can tell "no rows" from "one row that
        happened to be blank".
        """
        rows = content.get("rows") or []
        if not rows:
            return ""
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in rows[0]})
        return buffer.getvalue()

    @staticmethod
    def to_markdown(content: dict[str, Any], *, title: str = "Compliance report") -> str:
        """Render a report as a Markdown table."""
        rows = content.get("rows") or []
        if not rows:
            return f"# {title}\n\nNo rows.\n"
        headers = list(rows[0].keys())
        lines = [f"# {title}", "", "| " + " | ".join(headers) + " |"]
        lines.append("| " + " | ".join("---" for _ in headers) + " |")
        for row in rows:
            lines.append("| " + " | ".join(str(row.get(key, "")) for key in headers) + " |")
        return "\n".join(lines) + "\n"


class AuditService:
    """Writes and reads the append-only compliance audit trail."""

    def __init__(
        self,
        audits: AuditRepository,
        *,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self._audits = audits
        self._session_factory = session_factory

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
    ) -> ComplianceAudit:
        """Append one entry."""
        return await self._audits.create(
            ComplianceAudit(
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

    async def record_failure(
        self,
        organization_id: UUID,
        *,
        action: AuditAction,
        entity_type: str,
        summary: str,
        entity_reference: str | None = None,
        actor_id: str | None = None,
        request_id: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Append an entry for an operation that was refused.

        Committed in its **own transaction**. A refused request's
        transaction rolls back -- that is what refusing it means -- and
        an audit row written inside it would roll back too. The record of
        the attempt would be lost exactly when it matters most, because a
        refused attempt is the one an investigation asks about.
        """
        if self._session_factory is None:
            await self.record(
                organization_id,
                action=action,
                entity_type=entity_type,
                summary=summary,
                entity_reference=entity_reference,
                actor_id=actor_id,
                succeeded=False,
                request_id=request_id,
                context=context,
            )
            return

        async with session_scope(self._session_factory) as session:
            await AuditRepository(session).create(
                ComplianceAudit(
                    organization_id=organization_id,
                    action=action,
                    entity_type=entity_type,
                    entity_reference=entity_reference,
                    actor_id=actor_id,
                    actor_type="user",
                    occurred_at=datetime.now(UTC),
                    summary=summary,
                    succeeded=False,
                    request_id=request_id,
                    context=dict(context or {}),
                )
            )

    async def list_entries(
        self,
        organization_id: UUID,
        *,
        entity_type: str | None = None,
        entity_id: UUID | None = None,
        actor_id: str | None = None,
        since: datetime | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[ComplianceAudit]:
        """Audit entries, newest first."""
        return await self._audits.list_for_org(
            organization_id,
            entity_type=entity_type,
            entity_id=entity_id,
            actor_id=actor_id,
            since=since,
            limit=limit,
            offset=offset,
        )

    async def summary(self, organization_id: UUID, *, days: int = 30) -> dict[str, Any]:
        """How much of each action has happened lately."""
        since = datetime.now(UTC) - timedelta(days=days)
        counts = await self._audits.count_by_action(organization_id, since=since)
        return {
            "since": since.isoformat(),
            "total": sum(counts.values()),
            "by_action": counts,
        }


__all__ = ["AuditService", "ReportService", "StatisticsService"]
