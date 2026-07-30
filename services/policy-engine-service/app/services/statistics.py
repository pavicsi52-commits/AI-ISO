"""Analytics and reports (docs/050 "ANALYTICS", "REPORTING").

**Every figure is derived, never incremented.** A counter bumped per
decision drifts the moment one write is lost, and nothing can tell you
it has. Recomputing means every number is explainable by rows somebody
can go and count.

Two figures are worth more than they look:

- **Unused policies** -- published rules nothing has ever matched.
  Either dead weight or, far more dangerously, a rule whose conditions
  have drifted out of line with reality: it looks like governance and
  enforces nothing.
- **p95 latency**, reported alongside the mean rather than instead of it.
  A mean is dominated by the fast majority; the tail is what a caller
  with a request timeout actually experiences.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.logging.logger import get_logger

from app.models.enums import ApprovalStatus, JobStatus, PolicyStatus, ReportKind
from app.models.operations import PolicyReport, PolicyStatistics
from app.repositories.policy import PolicyRepository
from app.repositories.runtime import (
    PolicyApprovalRepository,
    PolicyDecisionRepository,
    PolicyReportRepository,
    PolicyStatisticsRepository,
    PolicyViolationRepository,
)
from app.services.compliance import status_of as violation_status_of

logger = get_logger("app.services.statistics")

_TOP_POLICIES = 20


class StatisticsService:
    """Computes and stores an organization's policy analytics."""

    def __init__(
        self,
        policies: PolicyRepository,
        decisions: PolicyDecisionRepository,
        violations: PolicyViolationRepository,
        approvals: PolicyApprovalRepository,
        statistics: PolicyStatisticsRepository,
    ) -> None:
        self._policies = policies
        self._decisions = decisions
        self._violations = violations
        self._approvals = approvals
        self._statistics = statistics

    async def compute(self, organization_id: UUID) -> dict[str, Any]:
        """Compute a rollup without storing it.

        Every read is sequential. An ``AsyncSession`` is not safe for
        concurrent use even for reads, so gathering these would be a
        latent ``InterfaceError`` under load rather than a speed-up.
        """
        by_status = await self._policies.count_by_status(organization_id)
        decision_stats = await self._decisions.statistics_for_org(organization_id)
        p95 = await self._decisions.percentile_latency(organization_id, fraction=0.95)
        by_effect = await self._decisions.counts_by_effect(organization_id)
        unused = await self._policies.list_unused(organization_id, limit=500)

        violations = await self._violations.list_for_org(organization_id, limit=1_000)
        approvals = await self._approvals.list_for_org(organization_id, limit=1_000)

        quota_violations = int(by_effect.get("quota_exceeded", 0))
        approval_required = int(by_effect.get("require_approval", 0))

        return {
            "policy_count": sum(by_status.values()),
            "published_count": int(by_status.get(str(PolicyStatus.PUBLISHED), 0)),
            "draft_count": int(by_status.get(str(PolicyStatus.DRAFT), 0)),
            "decision_count": int(decision_stats["total"]),
            "allowed_count": int(decision_stats["allowed"]),
            "denied_count": int(decision_stats["denied"]),
            "approval_required_count": approval_required,
            "violation_count": len(violations),
            "open_violation_count": sum(
                1 for one in violations if str(violation_status_of(one)) == "open"
            ),
            "quota_violation_count": quota_violations,
            "pending_approval_count": sum(
                1 for one in approvals if str(one.status) == str(ApprovalStatus.PENDING)
            ),
            "expired_approval_count": sum(
                1 for one in approvals if str(one.status) == str(ApprovalStatus.EXPIRED)
            ),
            "average_latency_ms": round(decision_stats["average_ms"], 4),
            "p95_latency_ms": round(p95, 4),
            "unused_policy_count": len(unused),
            "policy_usage": await self._policy_usage(organization_id),
            "decisions_by_effect": by_effect,
            "decisions_by_category": await self._decisions_by_category(organization_id),
        }

    async def refresh(self, organization_id: UUID) -> PolicyStatistics:
        """Recompute and persist the rollup.

        Updated in place rather than appended: the decisions and
        violations are the history, and a second time series of the same
        numbers would only be another thing to keep consistent with them.
        """
        values = await self.compute(organization_id)
        existing = await self._statistics.get_for_org(organization_id)
        if existing is not None:
            for column, value in values.items():
                setattr(existing, column, value)
            existing.computed_at = datetime.now(UTC)
            return await self._statistics.update(existing)
        return await self._statistics.create(
            PolicyStatistics(
                organization_id=organization_id,
                computed_at=datetime.now(UTC),
                **values,
            )
        )

    async def get(self, organization_id: UUID) -> PolicyStatistics | None:
        """The stored rollup, or ``None`` if none has been computed."""
        return await self._statistics.get_for_org(organization_id)

    async def _policy_usage(self, organization_id: UUID) -> dict[str, Any]:
        """Which policies are actually matching, most-used first.

        Read from each policy's own counter rather than by grouping the
        decision log: the counter is what survives decision retention,
        and "this rule has never fired in a year" is a question asked
        long after the decisions themselves have been swept.
        """
        rows = await self._policies.list_for_org(
            organization_id, status=PolicyStatus.PUBLISHED, limit=1_000
        )
        ranked = sorted(rows, key=lambda one: (-one.evaluation_count, one.slug))
        return {
            "most_used": [
                {"slug": one.slug, "evaluations": one.evaluation_count}
                for one in ranked[:_TOP_POLICIES]
            ],
            "never_used": [one.slug for one in ranked if one.evaluation_count == 0][:_TOP_POLICIES],
        }

    async def _decisions_by_category(self, organization_id: UUID) -> dict[str, int]:
        """Decisions grouped by the category of the policy that decided them.

        Derived by joining the deciding policy rather than stored on the
        decision, because a decision's category is a property of the
        policy that won -- and recording it twice would let the two
        disagree after a policy was recategorised.
        """
        decisions = await self._decisions.list_for_org(organization_id, limit=1_000)
        policies = {
            one.id: str(one.category)
            for one in await self._policies.list_for_org(organization_id, limit=1_000)
        }
        counts: dict[str, int] = {}
        for decision in decisions:
            category = policies.get(decision.deciding_policy_id or UUID(int=0), "none")
            counts[category] = counts.get(category, 0) + 1
        return counts


class ReportService:
    """Generates and stores policy reports."""

    def __init__(
        self,
        reports: PolicyReportRepository,
        policies: PolicyRepository,
        decisions: PolicyDecisionRepository,
        violations: PolicyViolationRepository,
        approvals: PolicyApprovalRepository,
        statistics: StatisticsService,
    ) -> None:
        self._reports = reports
        self._policies = policies
        self._decisions = decisions
        self._violations = violations
        self._approvals = approvals
        self._statistics = statistics

    async def generate(
        self,
        organization_id: UUID,
        *,
        kind: ReportKind,
        title: str | None = None,
        parameters: dict[str, Any] | None = None,
        actor_id: UUID | None = None,
    ) -> PolicyReport:
        """Build one report and store it with its payload.

        Never raises for a content failure -- the error lands on the row
        and is returned, because a caller who asked for a report needs to
        be told what went wrong with it rather than handed a stack trace.
        """
        record = await self._reports.create(
            PolicyReport(
                organization_id=organization_id,
                title=title or f"{str(kind).replace('_', ' ').title()} report",
                kind=kind,
                status=JobStatus.RUNNING,
                parameters=parameters or {},
                generated_at=datetime.now(UTC),
                generated_by=actor_id,
                created_by=actor_id,
            )
        )
        started = datetime.now(UTC)
        try:
            content = await self._content_for(organization_id, kind, parameters or {})
            payload = json.dumps(content, default=str, indent=2).encode("utf-8")
            record.content = content
            record.summary = str(content.get("summary") or "")
            record.payload = payload
            record.size_bytes = len(payload)
            record.checksum_sha256 = hashlib.sha256(payload).hexdigest()
            record.content_type = "application/json"
            record.status = JobStatus.SUCCEEDED
        except Exception as exc:
            record.status = JobStatus.FAILED
            record.error = str(exc)
            logger.warning(
                "A policy report failed to generate.",
                extra={"extra_fields": {"kind": str(kind), "error": str(exc)}},
            )

        record.duration_ms = (datetime.now(UTC) - started).total_seconds() * 1000
        return await self._reports.update(record)

    async def _content_for(
        self, organization_id: UUID, kind: ReportKind, parameters: dict[str, Any]
    ) -> dict[str, Any]:
        """Build one report's body.

        A dispatch table rather than a chain of branches, so a
        :class:`~app.models.enums.ReportKind` added without a builder
        fails loudly here instead of producing an empty report that looks
        like an organization with nothing to report.
        """
        builders = {
            ReportKind.POLICY: self._policy_report,
            ReportKind.VIOLATION: self._violation_report,
            ReportKind.COMPLIANCE: self._compliance_report,
            ReportKind.DECISION: self._decision_report,
            ReportKind.APPROVAL: self._approval_report,
            ReportKind.EXECUTIVE: self._executive_report,
        }
        builder = builders.get(kind)
        if builder is None:
            raise ValueError(f"No report builder for kind {str(kind)!r}.")
        return await builder(organization_id, parameters)

    async def _policy_report(
        self, organization_id: UUID, _parameters: dict[str, Any]
    ) -> dict[str, Any]:
        """The catalogue, and what is not being used."""
        rows = await self._policies.list_for_org(organization_id, limit=1_000)
        unused = await self._policies.list_unused(organization_id, limit=500)
        return {
            "summary": (
                f"{len(rows)} policies, {len(unused)} of them published but never matched."
            ),
            "policies": [
                {
                    "slug": one.slug,
                    "name": one.name,
                    "status": str(one.status),
                    "effect": str(one.effect),
                    "category": str(one.category),
                    "priority": one.priority,
                    "version": one.version,
                    "evaluations": one.evaluation_count,
                }
                for one in rows
            ],
            "never_matched": [one.slug for one in unused],
        }

    async def _violation_report(
        self, organization_id: UUID, _parameters: dict[str, Any]
    ) -> dict[str, Any]:
        """Every recorded breach, open first."""
        rows = await self._violations.list_for_org(organization_id, limit=1_000)
        open_rows = [one for one in rows if str(violation_status_of(one)) == "open"]
        return {
            "summary": f"{len(rows)} violations, {len(open_rows)} still open.",
            "open_count": len(open_rows),
            "violations": [
                {
                    "title": one.title,
                    "severity": one.severity,
                    "standard": str(one.standard),
                    "status": str(one.status),
                    "detected_at": one.detected_at.isoformat(),
                    "resolution_note": one.resolution_note,
                }
                for one in rows
            ],
        }

    async def _compliance_report(
        self, organization_id: UUID, _parameters: dict[str, Any]
    ) -> dict[str, Any]:
        """Violations grouped by the standard they breached."""
        rows = await self._violations.list_for_org(organization_id, limit=1_000)
        by_standard: dict[str, dict[str, int]] = {}
        for one in rows:
            bucket = by_standard.setdefault(str(one.standard), {"total": 0, "open": 0})
            bucket["total"] += 1
            if str(violation_status_of(one)) == "open":
                bucket["open"] += 1
        return {
            "summary": (f"{len(rows)} violations across {len(by_standard)} compliance standards."),
            "by_standard": by_standard,
        }

    async def _decision_report(
        self, organization_id: UUID, _parameters: dict[str, Any]
    ) -> dict[str, Any]:
        """Decision counts, latency, and the recent refusals."""
        stats = await self._decisions.statistics_for_org(organization_id)
        by_effect = await self._decisions.counts_by_effect(organization_id)
        refused = await self._decisions.list_for_org(organization_id, denied_only=True, limit=100)
        return {
            "summary": (
                f"{int(stats['total'])} decisions: {int(stats['allowed'])} allowed, "
                f"{int(stats['denied'])} refused."
            ),
            "counts": {k: int(v) for k, v in stats.items()},
            "by_effect": by_effect,
            "recent_refusals": [
                {
                    "subject_id": one.subject_id,
                    "resource": f"{one.resource_type}:{one.resource_id or '*'}",
                    "action": str(one.action),
                    "effect": str(one.effect),
                    "reason": one.reason,
                    "decided_at": one.decided_at.isoformat(),
                }
                for one in refused
            ],
        }

    async def _approval_report(
        self, organization_id: UUID, _parameters: dict[str, Any]
    ) -> dict[str, Any]:
        """Approvals, with the break-glass ones called out.

        Emergency approvals get their own section rather than being one
        row among many. They are the entries a reviewer is looking for,
        and a report that buries them in a list of two hundred has hidden
        them.
        """
        rows = await self._approvals.list_for_org(organization_id, limit=1_000)
        emergency = [one for one in rows if one.is_emergency]
        by_status: dict[str, int] = {}
        for one in rows:
            key = str(one.status)
            by_status[key] = by_status.get(key, 0) + 1
        return {
            "summary": (
                f"{len(rows)} approval requests, {len(emergency)} of them emergency (break-glass)."
            ),
            "by_status": by_status,
            "emergency_approvals": [
                {
                    "subject_id": one.subject_id,
                    "resource": f"{one.resource_type}:{one.resource_id or '*'}",
                    "action": str(one.action),
                    "status": str(one.status),
                    "requested_at": one.requested_at.isoformat(),
                    "reason": one.reason,
                }
                for one in emergency
            ],
        }

    async def _executive_report(
        self, organization_id: UUID, _parameters: dict[str, Any]
    ) -> dict[str, Any]:
        """The one-page view, leading with what needs attention."""
        values = await self._statistics.compute(organization_id)
        attention: list[str] = []
        if values["open_violation_count"]:
            attention.append(f"{values['open_violation_count']} open violations")
        if values["pending_approval_count"]:
            attention.append(f"{values['pending_approval_count']} approvals waiting")
        if values["unused_policy_count"]:
            attention.append(
                f"{values['unused_policy_count']} published policies have never matched"
            )
        if values["quota_violation_count"]:
            attention.append(f"{values['quota_violation_count']} quota refusals")

        return {
            "summary": (
                "; ".join(attention) if attention else "Nothing currently needs attention."
            ),
            "needs_attention": attention,
            "policies": {
                "total": values["policy_count"],
                "published": values["published_count"],
                "draft": values["draft_count"],
                "never_matched": values["unused_policy_count"],
            },
            "decisions": {
                "total": values["decision_count"],
                "allowed": values["allowed_count"],
                "refused": values["denied_count"],
                "average_latency_ms": values["average_latency_ms"],
                "p95_latency_ms": values["p95_latency_ms"],
            },
            "governance": {
                "open_violations": values["open_violation_count"],
                "pending_approvals": values["pending_approval_count"],
                "quota_refusals": values["quota_violation_count"],
            },
        }

    async def get(self, organization_id: UUID, report_id: UUID) -> PolicyReport:
        """One report.

        Raises:
            NotFoundError: If it does not exist in this organization. A
                report payload can hold every decision an organization
                has made, so the ownership check is the difference
                between a download and a disclosure.
        """
        return await self._reports.require_by_id(organization_id, report_id)

    async def list_reports(
        self, organization_id: UUID, *, kind: ReportKind | None = None, limit: int = 100
    ) -> list[PolicyReport]:
        """Reports, most recent first."""
        return await self._reports.list_for_org(organization_id, kind=kind, limit=limit)

    def verify(self, report: PolicyReport) -> dict[str, Any]:
        """Check a stored report against its recorded digest."""
        if report.payload is None:
            return {"valid": False, "reason": "the report holds no payload"}
        computed = hashlib.sha256(report.payload).hexdigest()
        return {
            "valid": computed == report.checksum_sha256,
            "expected": report.checksum_sha256,
            "computed": computed,
            "size_bytes": len(report.payload),
        }


__all__ = ["ReportService", "StatisticsService"]
