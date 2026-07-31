"""Exceptions, the risk register, and remediation.

The three things an organization does about a finding it cannot or will
not fix immediately: waive it, record it as an accepted risk, or fix it
and prove the fix worked.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.validation import ValidationError
from shared_core.logging.logger import get_logger

from app.events.compliance_events import (
    SOURCE_SERVICE,
    ComplianceExceptionCreatedEvent,
    RemediationCompletedEvent,
    RiskRegisteredEvent,
)
from app.models.enums import (
    LIVE_EXCEPTION_STATUSES,
    ExceptionKind,
    ExceptionStatus,
    FindingStatus,
    RemediationKind,
    RemediationStatus,
    ResultStatus,
    RiskCategory,
    RiskImpact,
    RiskLikelihood,
    RiskStatus,
    exception_status_of,
    remediation_status_of,
    result_status_of,
    risk_status_of,
)
from app.models.evidence import ComplianceException
from app.models.governance import RemediationTask, RiskRegisterEntry
from app.notifications.compliance_notifications import ComplianceNotificationService
from app.repositories.catalogue import ControlRepository
from app.repositories.governance import (
    ExceptionRepository,
    FindingRepository,
    RemediationRepository,
    RiskRepository,
)
from app.repositories.runs import ResultRepository
from app.risk.engine import assess, next_reference, next_review, residual
from app.types import EventPublisher

logger = get_logger("app.services.governance")


class ExceptionService:
    """Waivers: requesting, approving, reviewing, and expiring them."""

    def __init__(
        self,
        exceptions: ExceptionRepository,
        controls: ControlRepository,
        notifications: ComplianceNotificationService,
        *,
        publish_event: EventPublisher | None = None,
        max_days: int = 365,
        review_interval_days: int = 90,
        expiry_warning_days: int = 14,
    ) -> None:
        self._exceptions = exceptions
        self._controls = controls
        self._notifications = notifications
        self._publish = publish_event
        self._max_days = max_days
        self._review_interval_days = review_interval_days
        self._expiry_warning_days = expiry_warning_days

    async def _publish_event(self, event: Any) -> None:
        if self._publish is not None:
            await self._publish(event)

    async def request(
        self,
        organization_id: UUID,
        *,
        control_id: UUID,
        title: str,
        business_justification: str,
        kind: ExceptionKind = ExceptionKind.TEMPORARY,
        expires_at: datetime | None = None,
        risk_acceptance: str | None = None,
        compensating_control: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        review_interval_days: int | None = None,
        requested_by: str | None = None,
        actor_id: UUID | None = None,
    ) -> ComplianceException:
        """Ask for a control to be waived.

        A temporary exception **must** carry an expiry, and that expiry
        is capped: "temporary" is the word people use for the waivers
        that outlive the systems they were granted for, so the ceiling is
        what makes the word mean something.

        A permanent exception may omit an expiry but still gets a review
        date. A waiver nobody ever looks at again is an undocumented
        policy change, whatever it is called.

        Raises:
            NotFoundError: If the control does not exist here.
            ValidationError: If a temporary waiver has no expiry, or one
                that is in the past or past the ceiling.
        """
        await self._controls.require_in_org(organization_id, control_id)
        if not business_justification.strip():
            raise ValidationError(
                "An exception needs a business justification. Without one it is "
                "indistinguishable from an oversight, and nobody can later ask "
                "whether the reason still holds."
            )

        now = datetime.now(UTC)
        if kind is not ExceptionKind.PERMANENT:
            if expires_at is None:
                raise ValidationError(
                    f"A {str(kind)!r} exception needs an expiry date. An exception "
                    "without one is a permanent exception that has not admitted it."
                )
            if expires_at <= now:
                raise ValidationError("An exception cannot expire in the past.")
            ceiling = now + timedelta(days=self._max_days)
            if expires_at > ceiling:
                raise ValidationError(
                    f"An exception may run at most {self._max_days} days before it is "
                    f"re-approved; {expires_at.isoformat()} is past that ceiling."
                )

        interval = review_interval_days or self._review_interval_days
        created = await self._exceptions.create(
            ComplianceException(
                organization_id=organization_id,
                control_id=control_id,
                title=title,
                kind=kind,
                status=ExceptionStatus.REQUESTED,
                business_justification=business_justification,
                risk_acceptance=risk_acceptance,
                compensating_control=compensating_control,
                target_type=target_type,
                target_id=target_id,
                requested_by=requested_by,
                requested_at=now,
                expires_at=expires_at,
                review_interval_days=interval,
                next_review_at=now + timedelta(days=interval),
                created_by=actor_id,
            )
        )

        await self._publish_event(
            ComplianceExceptionCreatedEvent(
                source_service=SOURCE_SERVICE,
                payload={
                    "organization_id": str(organization_id),
                    "exception_id": str(created.id),
                    "control_id": str(control_id),
                    "kind": str(kind),
                    "status": str(ExceptionStatus.REQUESTED),
                    "expires_at": expires_at.isoformat() if expires_at else None,
                },
            )
        )
        return created

    async def approve(
        self,
        organization_id: UUID,
        exception_id: UUID,
        *,
        approved_by: str,
        actor_id: UUID | None = None,
    ) -> ComplianceException:
        """Grant a requested waiver.

        Raises:
            ConflictError: If it is not awaiting a decision. Approving an
                already-approved waiver would reset its review clock, and
                approving a revoked one would silently resurrect a
                decision somebody deliberately took back.
        """
        stored = await self._exceptions.require_in_org(organization_id, exception_id)
        current = exception_status_of(stored)
        if current is not ExceptionStatus.REQUESTED:
            raise ConflictError(f"This exception is {str(current)!r}, not awaiting a decision.")
        now = datetime.now(UTC)
        stored.status = ExceptionStatus.ACTIVE
        stored.approved_by = approved_by
        stored.approved_at = now
        stored.effective_from = now
        stored.updated_by = actor_id
        return await self._exceptions.update(stored)

    async def reject(
        self,
        organization_id: UUID,
        exception_id: UUID,
        *,
        reason: str,
        actor_id: UUID | None = None,
    ) -> ComplianceException:
        """Refuse a requested waiver.

        Raises:
            ConflictError: If it is not awaiting a decision.
        """
        stored = await self._exceptions.require_in_org(organization_id, exception_id)
        if exception_status_of(stored) is not ExceptionStatus.REQUESTED:
            raise ConflictError("This exception is not awaiting a decision.")
        stored.status = ExceptionStatus.REJECTED
        stored.rejected_reason = reason
        stored.updated_by = actor_id
        return await self._exceptions.update(stored)

    async def revoke(
        self,
        organization_id: UUID,
        exception_id: UUID,
        *,
        reason: str,
        actor_id: UUID | None = None,
    ) -> ComplianceException:
        """End a live waiver early.

        Raises:
            ConflictError: If it is not currently in force.
        """
        stored = await self._exceptions.require_in_org(organization_id, exception_id)
        if exception_status_of(stored) not in LIVE_EXCEPTION_STATUSES:
            raise ConflictError("This exception is not in force.")
        stored.status = ExceptionStatus.REVOKED
        stored.revoked_at = datetime.now(UTC)
        stored.revoked_by = str(actor_id) if actor_id else None
        stored.revocation_reason = reason
        stored.updated_by = actor_id
        return await self._exceptions.update(stored)

    async def review(
        self,
        organization_id: UUID,
        exception_id: UUID,
        *,
        reviewed_by: str,
        still_needed: bool,
        note: str | None = None,
        actor_id: UUID | None = None,
    ) -> ComplianceException:
        """Record a periodic review, and act on its conclusion.

        A review that concludes the waiver is no longer needed revokes
        it. Recording "no longer needed" while leaving the waiver in
        force would be the worst of both worlds: the register would say
        the right thing while the estate kept behaving the old way.
        """
        stored = await self._exceptions.require_in_org(organization_id, exception_id)
        now = datetime.now(UTC)
        stored.last_reviewed_at = now
        stored.last_reviewed_by = reviewed_by
        stored.next_review_at = now + timedelta(days=stored.review_interval_days)
        stored.updated_by = actor_id

        if not still_needed:
            stored.status = ExceptionStatus.REVOKED
            stored.revoked_at = now
            stored.revoked_by = reviewed_by
            stored.revocation_reason = note or "A periodic review found it no longer needed."
        return await self._exceptions.update(stored)

    async def get(self, organization_id: UUID, exception_id: UUID) -> ComplianceException:
        """One exception.

        Raises:
            NotFoundError: If it does not exist here.
        """
        return await self._exceptions.require_in_org(organization_id, exception_id)

    async def list_exceptions(
        self,
        organization_id: UUID,
        *,
        status: ExceptionStatus | None = None,
        control_id: UUID | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[ComplianceException]:
        """Exceptions, newest first."""
        return await self._exceptions.list_filtered(
            organization_id, status=status, control_id=control_id, limit=limit, offset=offset
        )

    async def warn_expiring(
        self, organization_id: UUID, *, notify_user_id: str | None = None
    ) -> list[ComplianceException]:
        """Warn about waivers about to lapse.

        Sent before expiry, not after. A waiver that lapses unannounced
        turns into a wave of failing controls in the next assessment, and
        the first anybody hears of it is a dashboard going red for a
        reason nobody can explain.
        """
        horizon = datetime.now(UTC) + timedelta(days=self._expiry_warning_days)
        expiring = await self._exceptions.list_expiring(organization_id, before=horizon)
        if notify_user_id:
            for one in expiring:
                control = await self._controls.require_in_org(organization_id, one.control_id)
                await self._notifications.send_exception_expiring(
                    notify_user_id,
                    title=one.title,
                    expires_at=one.expires_at.isoformat() if one.expires_at else "never",
                    control_code=control.code,
                )
        return expiring

    async def expire_lapsed(self, organization_id: UUID) -> int:
        """Move every lapsed waiver to ``EXPIRED``."""
        changed = await self._exceptions.expire_lapsed(organization_id, now=datetime.now(UTC))
        if changed:
            logger.info(
                "Expired lapsed compliance exceptions.",
                extra={
                    "extra_fields": {
                        "organization_id": str(organization_id),
                        "count": changed,
                    }
                },
            )
        return changed

    async def due_for_review(
        self, organization_id: UUID, *, limit: int = 200
    ) -> list[ComplianceException]:
        """Live waivers whose review date has passed."""
        return await self._exceptions.list_due_for_review(
            organization_id, now=datetime.now(UTC), limit=limit
        )

    async def overused(
        self, organization_id: UUID, *, threshold: int = 100
    ) -> list[ComplianceException]:
        """Waivers relied on so often they have become the real policy.

        The number that makes a quiet problem visible: a waiver used a
        thousand times is not an exception, and nothing else in the
        system would ever say so.
        """
        return await self._exceptions.list_overused(organization_id, threshold=threshold)


class RiskService:
    """The risk register."""

    def __init__(
        self,
        risks: RiskRepository,
        notifications: ComplianceNotificationService,
        *,
        publish_event: EventPublisher | None = None,
        review_interval_days: int = 90,
    ) -> None:
        self._risks = risks
        self._notifications = notifications
        self._publish = publish_event
        self._review_interval_days = review_interval_days

    async def _publish_event(self, event: Any) -> None:
        if self._publish is not None:
            await self._publish(event)

    async def register(
        self,
        organization_id: UUID,
        *,
        title: str,
        likelihood: RiskLikelihood,
        impact: RiskImpact,
        category: RiskCategory = RiskCategory.COMPLIANCE,
        description: str | None = None,
        owner_id: str | None = None,
        owner_team: str | None = None,
        mitigation_plan: str | None = None,
        control_ids: list[str] | None = None,
        finding_ids: list[str] | None = None,
        review_interval_days: int | None = None,
        notify_user_id: str | None = None,
        actor_id: UUID | None = None,
    ) -> RiskRegisterEntry:
        """Add a risk to the register.

        Severity is **derived** from likelihood and impact, never taken
        from the caller. A register that accepts a severity lets the
        person who owns the risk grade their own risk, and the grade
        they choose is not the one the matrix gives.
        """
        scored = assess(likelihood, impact)
        now = datetime.now(UTC)
        interval = review_interval_days or self._review_interval_days
        reference = next_reference(await self._risks.existing_references(organization_id))

        created = await self._risks.create(
            RiskRegisterEntry(
                organization_id=organization_id,
                reference=reference,
                title=title,
                description=description,
                category=category,
                likelihood=likelihood,
                impact=impact,
                severity=scored.severity,
                inherent_score=scored.score,
                status=RiskStatus.IDENTIFIED,
                owner_id=owner_id,
                owner_team=owner_team,
                mitigation_plan=mitigation_plan,
                control_ids=list(control_ids or []),
                finding_ids=list(finding_ids or []),
                identified_at=now,
                review_interval_days=interval,
                next_review_at=now + timedelta(days=interval),
                created_by=actor_id,
            )
        )

        await self._publish_event(
            RiskRegisteredEvent(
                source_service=SOURCE_SERVICE,
                payload={
                    "organization_id": str(organization_id),
                    "risk_id": str(created.id),
                    "reference": reference,
                    "title": title,
                    "severity": str(scored.severity),
                    "score": scored.score,
                },
            )
        )
        if notify_user_id:
            await self._notifications.send_risk_registered(
                notify_user_id,
                reference=reference,
                title=title,
                severity=str(scored.severity),
            )
        return created

    async def update_assessment(
        self,
        organization_id: UUID,
        risk_id: UUID,
        *,
        likelihood: RiskLikelihood | None = None,
        impact: RiskImpact | None = None,
        residual_likelihood: RiskLikelihood | None = None,
        residual_impact: RiskImpact | None = None,
        actor_id: UUID | None = None,
    ) -> RiskRegisterEntry:
        """Re-score a risk, inherent or residual.

        Residual scoring needs **both** halves. Carrying the inherent
        likelihood forward when only the impact was given would report a
        mitigation as having reduced risk it never touched -- the
        specific way registers come to overstate how well a programme is
        doing.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stored = await self._risks.require_in_org(organization_id, risk_id)
        if likelihood is not None or impact is not None:
            scored = assess(
                likelihood or RiskLikelihood(str(stored.likelihood)),
                impact or RiskImpact(str(stored.impact)),
            )
            stored.likelihood = scored.likelihood
            stored.impact = scored.impact
            stored.severity = scored.severity
            stored.inherent_score = scored.score

        left = residual(residual_likelihood, residual_impact)
        if left is not None:
            stored.residual_likelihood = left.likelihood
            stored.residual_impact = left.impact
            stored.residual_severity = left.severity
            stored.residual_score = left.score
        stored.updated_by = actor_id
        return await self._risks.update(stored)

    async def transition(
        self,
        organization_id: UUID,
        risk_id: UUID,
        *,
        target: RiskStatus,
        reason: str | None = None,
        actor_id: UUID | None = None,
    ) -> RiskRegisterEntry:
        """Move a risk through its lifecycle.

        Raises:
            ConflictError: If it is already closed.
            ValidationError: If closing without a reason. A risk that
                left the register without an explanation is the one an
                auditor will ask about.
        """
        stored = await self._risks.require_in_org(organization_id, risk_id)
        if risk_status_of(stored) is RiskStatus.CLOSED:
            raise ConflictError("This risk is already closed.")
        if target is RiskStatus.CLOSED:
            if not (reason or "").strip():
                raise ValidationError("Closing a risk needs a reason.")
            stored.closed_at = datetime.now(UTC)
            stored.closure_reason = reason
        stored.status = target
        stored.updated_by = actor_id
        return await self._risks.update(stored)

    async def record_review(
        self, organization_id: UUID, risk_id: UUID, *, actor_id: UUID | None = None
    ) -> RiskRegisterEntry:
        """Note that somebody looked at a risk, and reset its clock."""
        stored = await self._risks.require_in_org(organization_id, risk_id)
        now = datetime.now(UTC)
        stored.last_reviewed_at = now
        stored.next_review_at = next_review(
            last_reviewed=now,
            interval_days=stored.review_interval_days,
            created_at=stored.identified_at,
        )
        stored.updated_by = actor_id
        return await self._risks.update(stored)

    async def get(self, organization_id: UUID, risk_id: UUID) -> RiskRegisterEntry:
        """One risk.

        Raises:
            NotFoundError: If it does not exist here.
        """
        return await self._risks.require_in_org(organization_id, risk_id)

    async def list_risks(
        self,
        organization_id: UUID,
        *,
        status: RiskStatus | None = None,
        owner_id: str | None = None,
        open_only: bool = False,
        limit: int = 200,
        offset: int = 0,
    ) -> list[RiskRegisterEntry]:
        """Risks, worst first."""
        return await self._risks.list_filtered(
            organization_id,
            status=status,
            owner_id=owner_id,
            open_only=open_only,
            limit=limit,
            offset=offset,
        )

    async def due_for_review(
        self, organization_id: UUID, *, limit: int = 200
    ) -> list[RiskRegisterEntry]:
        """Open risks whose review date has passed."""
        return await self._risks.list_due_for_review(
            organization_id, now=datetime.now(UTC), limit=limit
        )


class RemediationService:
    """Fixing findings, and proving the fix worked."""

    def __init__(
        self,
        remediations: RemediationRepository,
        findings: FindingRepository,
        results: ResultRepository,
        notifications: ComplianceNotificationService,
        *,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._remediations = remediations
        self._findings = findings
        self._results = results
        self._notifications = notifications
        self._publish = publish_event

    async def _publish_event(self, event: Any) -> None:
        if self._publish is not None:
            await self._publish(event)

    async def propose(
        self,
        organization_id: UUID,
        *,
        finding_id: UUID,
        title: str,
        kind: RemediationKind = RemediationKind.MANUAL,
        description: str | None = None,
        recommended_action: str | None = None,
        playbook_id: str | None = None,
        workflow_id: str | None = None,
        automation_job_id: str | None = None,
        assignee_id: str | None = None,
        due_at: datetime | None = None,
        actor_id: UUID | None = None,
    ) -> RemediationTask:
        """Propose a fix for a finding.

        Raises:
            NotFoundError: If the finding does not exist here.
        """
        finding = await self._findings.require_in_org(organization_id, finding_id)
        created = await self._remediations.create(
            RemediationTask(
                organization_id=organization_id,
                finding_id=finding_id,
                control_id=finding.control_id,
                title=title,
                description=description,
                kind=kind,
                status=RemediationStatus.PROPOSED,
                recommended_action=recommended_action,
                playbook_id=playbook_id,
                workflow_id=workflow_id,
                automation_job_id=automation_job_id,
                assignee_id=assignee_id,
                due_at=due_at,
                created_by=actor_id,
            )
        )
        if assignee_id:
            finding.status = FindingStatus.IN_PROGRESS
            finding.assignee_id = finding.assignee_id or assignee_id
            await self._findings.update(finding)
        return created

    async def transition(
        self,
        organization_id: UUID,
        task_id: UUID,
        *,
        target: RemediationStatus,
        note: str | None = None,
        actor_id: UUID | None = None,
    ) -> RemediationTask:
        """Move a remediation through its lifecycle.

        ``VERIFIED`` cannot be set here -- see :meth:`verify`.

        Raises:
            ConflictError: If ``VERIFIED`` is requested directly.
        """
        stored = await self._remediations.require_in_org(organization_id, task_id)
        if target is RemediationStatus.VERIFIED:
            raise ConflictError(
                "A remediation becomes VERIFIED only when a re-assessment confirms the "
                "control passes. Call verify() with a fresh result instead."
            )
        now = datetime.now(UTC)
        if target is RemediationStatus.IN_PROGRESS and stored.started_at is None:
            stored.started_at = now
            stored.attempts += 1
        if target is RemediationStatus.COMPLETED:
            stored.completed_at = now
        if target is RemediationStatus.FAILED:
            stored.error = note
        stored.status = target
        stored.updated_by = actor_id
        return await self._remediations.update(stored)

    async def verify(
        self,
        organization_id: UUID,
        task_id: UUID,
        *,
        verified_by: str,
        notify_user_id: str | None = None,
        actor_id: UUID | None = None,
    ) -> tuple[RemediationTask, bool]:
        """Check whether the control actually passes now.

        Returns the task and whether verification succeeded.

        **This reads a fresh result rather than trusting the caller.**
        "We ran the playbook" and "the control now passes" are different
        claims, and only the second may close a finding. An automated
        remediation that failed silently would otherwise close the
        finding it did not fix -- and that finding is then invisible
        until the next audit.

        Raises:
            NotFoundError: If the task does not exist here.
            ConflictError: If the fix has not been completed yet.
        """
        stored = await self._remediations.require_in_org(organization_id, task_id)
        if remediation_status_of(stored) not in (
            RemediationStatus.COMPLETED,
            RemediationStatus.FAILED,
        ):
            raise ConflictError(
                f"This remediation is {str(stored.status)!r}; there is nothing to verify "
                "until it has been carried out."
            )
        if stored.control_id is None:
            raise ConflictError(
                "This remediation is not attached to a control, so there is no control "
                "to re-assess."
            )

        finding = (
            await self._findings.require_in_org(organization_id, stored.finding_id)
            if stored.finding_id
            else None
        )
        latest = await self._results.latest_for_control_target(
            organization_id,
            stored.control_id,
            finding.target_id if finding else None,
        )

        now = datetime.now(UTC)
        passed = latest is not None and result_status_of(latest) in (
            ResultStatus.PASS,
            ResultStatus.NOT_APPLICABLE,
        )

        if not passed:
            stored.verification_note = (
                "The control has not been re-assessed since the fix."
                if latest is None
                else f"The most recent assessment still reports {str(latest.status)!r}."
            )
            stored.updated_by = actor_id
            await self._remediations.update(stored)
            logger.info(
                "A remediation was not verified; the control does not yet pass.",
                extra={
                    "extra_fields": {
                        "organization_id": str(organization_id),
                        "task_id": str(task_id),
                        "latest_status": str(latest.status) if latest else None,
                    }
                },
            )
            if notify_user_id:
                await self._notifications.send_remediation_completed(
                    notify_user_id, title=stored.title, verified=False
                )
            return stored, False

        stored.status = RemediationStatus.VERIFIED
        stored.verified_at = now
        stored.verified_by = verified_by
        stored.verification_result_id = latest.id if latest else None
        stored.verification_note = "A re-assessment confirms the control now passes."
        stored.updated_by = actor_id
        verified = await self._remediations.update(stored)

        if finding is not None:
            finding.status = FindingStatus.VERIFIED
            finding.resolved_at = now
            finding.resolved_by = verified_by
            finding.resolution_note = (
                f"Closed by remediation {stored.title!r}, confirmed by re-assessment."
            )
            await self._findings.update(finding)

        await self._publish_event(
            RemediationCompletedEvent(
                source_service=SOURCE_SERVICE,
                payload={
                    "organization_id": str(organization_id),
                    "task_id": str(task_id),
                    "finding_id": str(stored.finding_id) if stored.finding_id else None,
                    "control_id": str(stored.control_id),
                    "verified": True,
                },
            )
        )
        if notify_user_id:
            await self._notifications.send_remediation_completed(
                notify_user_id, title=stored.title, verified=True
            )
        return verified, True

    async def get(self, organization_id: UUID, task_id: UUID) -> RemediationTask:
        """One remediation task.

        Raises:
            NotFoundError: If it does not exist here.
        """
        return await self._remediations.require_in_org(organization_id, task_id)

    async def list_tasks(
        self,
        organization_id: UUID,
        *,
        status: RemediationStatus | None = None,
        assignee_id: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[RemediationTask]:
        """Remediation tasks, newest first."""
        return await self._remediations.list_filtered(
            organization_id, status=status, assignee_id=assignee_id, limit=limit, offset=offset
        )

    async def for_finding(self, organization_id: UUID, finding_id: UUID) -> list[RemediationTask]:
        """Every attempt to fix one finding."""
        return await self._remediations.list_for_finding(organization_id, finding_id)


__all__ = ["ExceptionService", "RemediationService", "RiskService"]
