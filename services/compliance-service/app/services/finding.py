"""Findings: raising them, deduplicating them, and closing them.

The module where a compliance programme becomes a queue somebody works,
which means the important behaviour is not raising findings but *not*
raising them twice.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.exceptions.conflict import ConflictError
from shared_core.logging.logger import get_logger

from app.assessments.engine import ControlResult, finding_severity_for
from app.events.compliance_events import SOURCE_SERVICE, ComplianceViolationDetectedEvent
from app.models.enums import (
    OPEN_FINDING_STATUSES,
    FindingSeverity,
    FindingStatus,
    finding_severity_of,
    finding_status_of,
)
from app.models.evidence import ComplianceFinding
from app.notifications.compliance_notifications import ComplianceNotificationService
from app.repositories.governance import FindingRepository
from app.risk.engine import due_at, fingerprint, risk_score_for_finding
from app.types import EventPublisher

logger = get_logger("app.services.finding")

_CLOSED_STATUSES = frozenset(
    {
        FindingStatus.VERIFIED,
        FindingStatus.RISK_ACCEPTED,
        FindingStatus.FALSE_POSITIVE,
        FindingStatus.CLOSED,
    }
)


class FindingService:
    """Raises, deduplicates, assigns, and closes findings."""

    def __init__(
        self,
        findings: FindingRepository,
        notifications: ComplianceNotificationService,
        *,
        publish_event: EventPublisher | None = None,
        critical_days: int = 7,
        high_days: int = 30,
        medium_days: int = 90,
        low_days: int = 180,
    ) -> None:
        self._findings = findings
        self._notifications = notifications
        self._publish = publish_event
        self._due_days = {
            "critical": critical_days,
            "high": high_days,
            "medium": medium_days,
            "low": low_days,
        }

    async def _publish_event(self, event: Any) -> None:
        if self._publish is not None:
            await self._publish(event)

    async def raise_from_result(
        self,
        organization_id: UUID,
        result: ControlResult,
        *,
        assessment_id: UUID | None = None,
        result_id: UUID | None = None,
        control_code: str | None = None,
        now: datetime | None = None,
        actor_id: UUID | None = None,
    ) -> tuple[ComplianceFinding, bool]:
        """Raise a finding, or update the existing one for this problem.

        Returns the finding and whether it was newly created.

        **The deduplication is the point.** A daily assessment across a
        thousand hosts would otherwise raise a third of a million
        findings a year for problems that never changed. Worse, each new
        finding resets the age -- and age is the only number that makes
        an overdue problem visible, so an un-deduplicated queue hides
        precisely the things that have been broken longest.

        A re-detected problem that somebody closed reopens the original
        rather than creating a second one beside it: two findings for one
        problem is how a queue stops being trustworthy.
        """
        moment = now or datetime.now(UTC)
        identity = fingerprint(
            control_id=result.control_id,
            target_id=result.target_id,
            target_type=result.target_type,
        )
        severity = finding_severity_for(result.severity)
        existing = await self._findings.get_by_fingerprint(organization_id, identity)

        if existing is not None:
            existing.last_detected_at = moment
            existing.detection_count += 1
            existing.risk_score = risk_score_for_finding(
                finding_severity_of(existing.severity),
                detection_count=existing.detection_count,
            )
            if finding_status_of(existing) in _CLOSED_STATUSES:
                # Reopened rather than duplicated. The resolution fields
                # are cleared because they describe a fix that evidently
                # did not hold, and leaving them would let a report claim
                # the problem was resolved on a date it demonstrably was
                # not.
                existing.status = FindingStatus.OPEN
                existing.resolved_at = None
                existing.resolved_by = None
                existing.resolution_note = (
                    f"Reopened {moment.isoformat()}: the control failed again."
                )
            existing.updated_by = actor_id
            return await self._findings.update(existing), False

        created = await self._findings.create(
            ComplianceFinding(
                organization_id=organization_id,
                assessment_id=assessment_id,
                result_id=result_id,
                control_id=UUID(result.control_id),
                framework_id=UUID(result.framework_id) if result.framework_id else None,
                title=f"{control_code or result.control_id} is not met on "
                f"{result.target_name or result.target_id or 'this organization'}",
                description=result.reason,
                severity=severity,
                status=FindingStatus.OPEN,
                fingerprint=identity,
                target_type=result.target_type,
                target_id=result.target_id or None,
                target_name=result.target_name,
                risk_score=risk_score_for_finding(severity),
                first_detected_at=moment,
                last_detected_at=moment,
                detection_count=1,
                due_at=due_at(
                    severity,
                    detected_at=moment,
                    critical_days=self._due_days["critical"],
                    high_days=self._due_days["high"],
                    medium_days=self._due_days["medium"],
                    low_days=self._due_days["low"],
                ),
                evidence_ids=[result.evidence_id] if result.evidence_id else [],
                exception_id=UUID(result.exception_id) if result.exception_id else None,
                created_by=actor_id,
            )
        )

        await self._publish_event(
            ComplianceViolationDetectedEvent(
                source_service=SOURCE_SERVICE,
                payload={
                    "organization_id": str(organization_id),
                    "finding_id": str(created.id),
                    "control_id": result.control_id,
                    "severity": str(severity),
                    "target_id": result.target_id,
                    "reason": result.reason,
                },
            )
        )
        return created, True

    async def get(self, organization_id: UUID, finding_id: UUID) -> ComplianceFinding:
        """One finding.

        Raises:
            NotFoundError: If it does not exist here.
        """
        return await self._findings.require_in_org(organization_id, finding_id)

    async def list_findings(
        self,
        organization_id: UUID,
        *,
        status: FindingStatus | None = None,
        severity: FindingSeverity | None = None,
        control_id: UUID | None = None,
        framework_id: UUID | None = None,
        assignee_id: str | None = None,
        target_id: str | None = None,
        open_only: bool = False,
        limit: int = 200,
        offset: int = 0,
    ) -> list[ComplianceFinding]:
        """Findings, worst and oldest first."""
        return await self._findings.list_filtered(
            organization_id,
            status=status,
            severity=severity,
            control_id=control_id,
            framework_id=framework_id,
            assignee_id=assignee_id,
            target_id=target_id,
            open_only=open_only,
            limit=limit,
            offset=offset,
        )

    async def assign(
        self,
        organization_id: UUID,
        finding_id: UUID,
        *,
        assignee_id: str,
        actor_id: UUID | None = None,
    ) -> ComplianceFinding:
        """Give a finding an owner.

        Raises:
            ConflictError: If it is already closed.
        """
        stored = await self._findings.require_in_org(organization_id, finding_id)
        if finding_status_of(stored) in _CLOSED_STATUSES:
            raise ConflictError("This finding is closed; reopen it before assigning it.")
        stored.assignee_id = assignee_id
        stored.assigned_at = datetime.now(UTC)
        if finding_status_of(stored) is FindingStatus.OPEN:
            stored.status = FindingStatus.ACKNOWLEDGED
        stored.updated_by = actor_id
        return await self._findings.update(stored)

    async def transition(
        self,
        organization_id: UUID,
        finding_id: UUID,
        *,
        target: FindingStatus,
        note: str | None = None,
        actor_id: UUID | None = None,
    ) -> ComplianceFinding:
        """Move a finding through its lifecycle.

        ``VERIFIED`` cannot be set here. That status means "a
        re-assessment confirmed the control now passes", which is a claim
        only :class:`~app.services.remediation.RemediationService` can
        make -- because only it has looked at the re-assessment. Letting
        a person set it by hand would make the one status that means
        *proven* mean *asserted*.

        Raises:
            ConflictError: If ``VERIFIED`` is requested directly.
        """
        stored = await self._findings.require_in_org(organization_id, finding_id)
        if target is FindingStatus.VERIFIED:
            raise ConflictError(
                "A finding becomes VERIFIED only when a re-assessment confirms the "
                "control passes. Record a remediation and verify it instead."
            )

        stored.status = target
        if target in _CLOSED_STATUSES:
            stored.resolved_at = datetime.now(UTC)
            stored.resolved_by = str(actor_id) if actor_id else None
            stored.resolution_note = note
        stored.updated_by = actor_id
        return await self._findings.update(stored)

    async def mark_verified(
        self,
        organization_id: UUID,
        finding_id: UUID,
        *,
        note: str,
        actor_id: UUID | None = None,
    ) -> ComplianceFinding:
        """Close a finding because a re-assessment proved the fix worked.

        Only ``RemediationService`` calls this, after reading a fresh
        result. Kept separate from :meth:`transition` so the distinction
        between "somebody says it is fixed" and "the control passes" is
        visible in the call graph rather than only in a comment.
        """
        stored = await self._findings.require_in_org(organization_id, finding_id)
        stored.status = FindingStatus.VERIFIED
        stored.resolved_at = datetime.now(UTC)
        stored.resolved_by = str(actor_id) if actor_id else None
        stored.resolution_note = note
        stored.updated_by = actor_id
        return await self._findings.update(stored)

    async def notify_critical(
        self,
        results: list[ControlResult],
        *,
        notify_user_id: str | None,
        control_codes: dict[str, str] | None = None,
    ) -> int:
        """Tell somebody about failures on critical controls.

        Only the criticals. A notification per failure would, on a real
        estate, mean thousands of emails from one assessment -- and an
        inbox nobody can read is the same as no notification at all.
        """
        if not notify_user_id or not results:
            return 0
        codes = control_codes or {}
        for one in results:
            await self._notifications.send_critical_failure(
                notify_user_id,
                control_code=codes.get(one.control_id, one.control_id),
                target=one.target_name or one.target_id or "the organization",
                detail=one.reason,
            )
        return len(results)

    async def overdue(
        self, organization_id: UUID, *, now: datetime | None = None, limit: int = 500
    ) -> list[ComplianceFinding]:
        """Open findings past their due date."""
        return await self._findings.list_overdue(
            organization_id, now=now or datetime.now(UTC), limit=limit
        )

    async def summary(self, organization_id: UUID) -> dict[str, Any]:
        """How the finding queue stands."""
        by_severity = await self._findings.count_by_severity(organization_id, open_only=True)
        overdue = await self.overdue(organization_id, limit=1_000)
        return {
            "open_total": await self._findings.count_open(organization_id),
            "by_severity": by_severity,
            "critical_open": by_severity.get(str(FindingSeverity.CRITICAL), 0),
            "overdue": len(overdue),
            "open_statuses": [str(one) for one in OPEN_FINDING_STATUSES],
        }


__all__ = ["FindingService"]
