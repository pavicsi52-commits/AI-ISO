"""Repositories for findings, exceptions, risk, remediation, and reporting."""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast
from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy import CursorResult, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import (
    LIVE_EXCEPTION_STATUSES,
    OPEN_FINDING_STATUSES,
    ExceptionStatus,
    FindingSeverity,
    FindingStatus,
    RemediationStatus,
    RiskStatus,
    ScoreScope,
)
from app.models.evidence import ComplianceException, ComplianceFinding
from app.models.governance import (
    ComplianceAudit,
    ComplianceHistory,
    ComplianceReport,
    ComplianceScore,
    ComplianceStatistic,
    RemediationTask,
    RiskRegisterEntry,
)


class FindingRepository(BaseRepository[ComplianceFinding]):
    """Controls that are not being met."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ComplianceFinding, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, finding_id: UUID) -> ComplianceFinding:
        """One finding by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(ComplianceFinding.organization_id == organization_id)
            .where(ComplianceFinding.id == finding_id)
        )
        result = await self._session.execute(stmt)
        found: ComplianceFinding | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No finding with id {finding_id} in this organization.")
        return found

    async def get_by_fingerprint(
        self, organization_id: UUID, fingerprint: str
    ) -> ComplianceFinding | None:
        """The existing finding for this problem on this thing, if any.

        The lookup that stops a daily assessment from raising 365
        findings for one unpatched host. Deliberately does **not**
        filter by status: a re-detected problem that somebody closed
        last week must reopen the original finding rather than creating
        a second one beside it, because two findings for one problem is
        how a queue stops being trustworthy.
        """
        stmt = (
            self._base_select()
            .where(ComplianceFinding.organization_id == organization_id)
            .where(ComplianceFinding.fingerprint == fingerprint)
            .order_by(ComplianceFinding.first_detected_at)
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_filtered(
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
        """Findings, worst and oldest first.

        Ordered by risk score then age rather than by creation, because
        a queue sorted by "newest" buries the thing that has been broken
        longest -- which is usually the thing that matters.
        """
        stmt = self._base_select().where(ComplianceFinding.organization_id == organization_id)
        if status is not None:
            stmt = stmt.where(ComplianceFinding.status == str(status))
        if open_only:
            stmt = stmt.where(
                ComplianceFinding.status.in_([str(one) for one in OPEN_FINDING_STATUSES])
            )
        if severity is not None:
            stmt = stmt.where(ComplianceFinding.severity == str(severity))
        if control_id is not None:
            stmt = stmt.where(ComplianceFinding.control_id == control_id)
        if framework_id is not None:
            stmt = stmt.where(ComplianceFinding.framework_id == framework_id)
        if assignee_id is not None:
            stmt = stmt.where(ComplianceFinding.assignee_id == assignee_id)
        if target_id is not None:
            stmt = stmt.where(ComplianceFinding.target_id == target_id)
        stmt = (
            stmt.order_by(
                ComplianceFinding.risk_score.desc(),
                ComplianceFinding.first_detected_at,
                ComplianceFinding.id,
            )
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_overdue(
        self, organization_id: UUID, *, now: datetime, limit: int = 500
    ) -> list[ComplianceFinding]:
        """Open findings past their due date."""
        stmt = (
            self._base_select()
            .where(ComplianceFinding.organization_id == organization_id)
            .where(ComplianceFinding.status.in_([str(one) for one in OPEN_FINDING_STATUSES]))
            .where(ComplianceFinding.due_at.isnot(None))
            .where(ComplianceFinding.due_at < now)
            .order_by(ComplianceFinding.due_at)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_severity(
        self, organization_id: UUID, *, open_only: bool = True
    ) -> dict[str, int]:
        """How many findings sit at each severity."""
        stmt = (
            select(ComplianceFinding.severity, func.count())
            .where(ComplianceFinding.organization_id == organization_id)
            .where(ComplianceFinding.deleted_at.is_(None))
        )
        if open_only:
            stmt = stmt.where(
                ComplianceFinding.status.in_([str(one) for one in OPEN_FINDING_STATUSES])
            )
        stmt = stmt.group_by(ComplianceFinding.severity)
        rows = (await self._session.execute(stmt)).all()
        return {str(severity): int(count) for severity, count in rows}

    async def count_open(self, organization_id: UUID) -> int:
        """How many findings are still outstanding."""
        stmt = (
            select(func.count())
            .select_from(ComplianceFinding)
            .where(ComplianceFinding.organization_id == organization_id)
            .where(ComplianceFinding.status.in_([str(one) for one in OPEN_FINDING_STATUSES]))
            .where(ComplianceFinding.deleted_at.is_(None))
        )
        return int((await self._session.execute(stmt)).scalar_one())

    async def count_in_window(
        self, organization_id: UUID, *, since: datetime, until: datetime, resolved: bool = False
    ) -> int:
        """How many findings opened, or closed, inside a window."""
        column = ComplianceFinding.resolved_at if resolved else ComplianceFinding.first_detected_at
        stmt = (
            select(func.count())
            .select_from(ComplianceFinding)
            .where(ComplianceFinding.organization_id == organization_id)
            .where(column.isnot(None))
            .where(column >= since)
            .where(column < until)
            .where(ComplianceFinding.deleted_at.is_(None))
        )
        return int((await self._session.execute(stmt)).scalar_one())


class ExceptionRepository(BaseRepository[ComplianceException]):
    """Controls consciously not met."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ComplianceException, tenant_scope=tenant_scope)

    async def require_in_org(
        self, organization_id: UUID, exception_id: UUID
    ) -> ComplianceException:
        """One exception by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(ComplianceException.organization_id == organization_id)
            .where(ComplianceException.id == exception_id)
        )
        result = await self._session.execute(stmt)
        found: ComplianceException | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No exception with id {exception_id} in this organization.")
        return found

    async def list_live(
        self, organization_id: UUID, *, moment: datetime, limit: int = 500
    ) -> list[ComplianceException]:
        """Waivers an assessment must honour right now.

        Expiry is checked in SQL rather than in Python because this list
        feeds every assessment: filtering afterwards would load waivers
        that expired years ago on every run, forever.
        """
        stmt = (
            self._base_select()
            .where(ComplianceException.organization_id == organization_id)
            .where(ComplianceException.status.in_([str(one) for one in LIVE_EXCEPTION_STATUSES]))
            .where(
                (ComplianceException.expires_at.is_(None))
                | (ComplianceException.expires_at > moment)
            )
            .where(
                (ComplianceException.effective_from.is_(None))
                | (ComplianceException.effective_from <= moment)
            )
            .order_by(ComplianceException.created_at)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_filtered(
        self,
        organization_id: UUID,
        *,
        status: ExceptionStatus | None = None,
        control_id: UUID | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[ComplianceException]:
        """Exceptions, newest first."""
        stmt = self._base_select().where(ComplianceException.organization_id == organization_id)
        if status is not None:
            stmt = stmt.where(ComplianceException.status == str(status))
        if control_id is not None:
            stmt = stmt.where(ComplianceException.control_id == control_id)
        stmt = (
            stmt.order_by(ComplianceException.created_at.desc(), ComplianceException.id)
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_expiring(
        self, organization_id: UUID, *, before: datetime, limit: int = 500
    ) -> list[ComplianceException]:
        """Live waivers about to lapse, so somebody can be told first."""
        stmt = (
            self._base_select()
            .where(ComplianceException.organization_id == organization_id)
            .where(ComplianceException.status.in_([str(one) for one in LIVE_EXCEPTION_STATUSES]))
            .where(ComplianceException.expires_at.isnot(None))
            .where(ComplianceException.expires_at <= before)
            .order_by(ComplianceException.expires_at)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_due_for_review(
        self, organization_id: UUID, *, now: datetime, limit: int = 500
    ) -> list[ComplianceException]:
        """Live waivers whose review date has passed.

        Including permanent ones, which is the whole reason permanent
        waivers still carry a review interval: an exception nobody ever
        looks at again is an undocumented policy change.
        """
        stmt = (
            self._base_select()
            .where(ComplianceException.organization_id == organization_id)
            .where(ComplianceException.status.in_([str(one) for one in LIVE_EXCEPTION_STATUSES]))
            .where(ComplianceException.next_review_at.isnot(None))
            .where(ComplianceException.next_review_at <= now)
            .order_by(ComplianceException.next_review_at)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def record_use(self, exception_id: UUID, *, moment: datetime) -> None:
        """Count one reliance on a waiver.

        A number nobody looks at until it is large, at which point it is
        the clearest evidence that a "temporary" exception has become the
        actual policy. Incremented in SQL so concurrent assessments do
        not lose counts to a read-modify-write race.
        """
        await self._session.execute(
            update(ComplianceException)
            .where(ComplianceException.id == exception_id)
            .values(
                use_count=ComplianceException.use_count + 1,
                last_used_at=moment,
            )
        )

    async def expire_lapsed(self, organization_id: UUID, *, now: datetime) -> int:
        """Move every lapsed waiver to ``EXPIRED``.

        Returns the number changed. Done in one statement rather than a
        loop because the sweep runs against every organization and the
        set can be large after a long outage.
        """
        result = cast(
            "CursorResult[Any]",
            await self._session.execute(
                update(ComplianceException)
                .where(ComplianceException.organization_id == organization_id)
                .where(
                    ComplianceException.status.in_([str(one) for one in LIVE_EXCEPTION_STATUSES])
                )
                .where(ComplianceException.expires_at.isnot(None))
                .where(ComplianceException.expires_at <= now)
                .values(status=str(ExceptionStatus.EXPIRED))
            ),
        )
        return int(result.rowcount or 0)

    async def count_active(self, organization_id: UUID) -> int:
        """How many waivers are currently in force."""
        stmt = (
            select(func.count())
            .select_from(ComplianceException)
            .where(ComplianceException.organization_id == organization_id)
            .where(ComplianceException.status.in_([str(one) for one in LIVE_EXCEPTION_STATUSES]))
            .where(ComplianceException.deleted_at.is_(None))
        )
        return int((await self._session.execute(stmt)).scalar_one())

    async def list_overused(
        self, organization_id: UUID, *, threshold: int = 100, limit: int = 100
    ) -> list[ComplianceException]:
        """Waivers relied on so often they have become the real policy."""
        stmt = (
            self._base_select()
            .where(ComplianceException.organization_id == organization_id)
            .where(ComplianceException.use_count >= threshold)
            .order_by(ComplianceException.use_count.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class RiskRepository(BaseRepository[RiskRegisterEntry]):
    """The risk register."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, RiskRegisterEntry, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, risk_id: UUID) -> RiskRegisterEntry:
        """One risk by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(RiskRegisterEntry.organization_id == organization_id)
            .where(RiskRegisterEntry.id == risk_id)
        )
        result = await self._session.execute(stmt)
        found: RiskRegisterEntry | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No risk with id {risk_id} in this organization.")
        return found

    async def existing_references(self, organization_id: UUID) -> list[str]:
        """Every reference already assigned, so the next one is unique.

        Includes soft-deleted rows on purpose: a reference is quoted in
        meeting minutes and audit reports, so reusing one that was
        deleted would make two different risks share an identifier in the
        written record.
        """
        stmt = select(RiskRegisterEntry.reference).where(
            RiskRegisterEntry.organization_id == organization_id
        )
        return [str(one) for one in (await self._session.execute(stmt)).scalars().all()]

    async def list_filtered(
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
        stmt = self._base_select().where(RiskRegisterEntry.organization_id == organization_id)
        if status is not None:
            stmt = stmt.where(RiskRegisterEntry.status == str(status))
        if open_only:
            stmt = stmt.where(RiskRegisterEntry.status != str(RiskStatus.CLOSED))
        if owner_id is not None:
            stmt = stmt.where(RiskRegisterEntry.owner_id == owner_id)
        stmt = (
            stmt.order_by(
                RiskRegisterEntry.inherent_score.desc(),
                RiskRegisterEntry.identified_at,
                RiskRegisterEntry.id,
            )
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_due_for_review(
        self, organization_id: UUID, *, now: datetime, limit: int = 200
    ) -> list[RiskRegisterEntry]:
        """Open risks whose review date has passed."""
        stmt = (
            self._base_select()
            .where(RiskRegisterEntry.organization_id == organization_id)
            .where(RiskRegisterEntry.status != str(RiskStatus.CLOSED))
            .where(RiskRegisterEntry.next_review_at.isnot(None))
            .where(RiskRegisterEntry.next_review_at <= now)
            .order_by(RiskRegisterEntry.next_review_at)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_open(self, organization_id: UUID) -> int:
        """How many risks are still live."""
        stmt = (
            select(func.count())
            .select_from(RiskRegisterEntry)
            .where(RiskRegisterEntry.organization_id == organization_id)
            .where(RiskRegisterEntry.status != str(RiskStatus.CLOSED))
            .where(RiskRegisterEntry.deleted_at.is_(None))
        )
        return int((await self._session.execute(stmt)).scalar_one())

    async def count_in_window(
        self, organization_id: UUID, *, since: datetime, until: datetime
    ) -> int:
        """How many risks were registered inside a window."""
        stmt = (
            select(func.count())
            .select_from(RiskRegisterEntry)
            .where(RiskRegisterEntry.organization_id == organization_id)
            .where(RiskRegisterEntry.identified_at >= since)
            .where(RiskRegisterEntry.identified_at < until)
            .where(RiskRegisterEntry.deleted_at.is_(None))
        )
        return int((await self._session.execute(stmt)).scalar_one())


class RemediationRepository(BaseRepository[RemediationTask]):
    """How findings get fixed."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, RemediationTask, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, task_id: UUID) -> RemediationTask:
        """One remediation task by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(RemediationTask.organization_id == organization_id)
            .where(RemediationTask.id == task_id)
        )
        result = await self._session.execute(stmt)
        found: RemediationTask | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No remediation task with id {task_id} in this organization.")
        return found

    async def list_for_finding(
        self, organization_id: UUID, finding_id: UUID
    ) -> list[RemediationTask]:
        """Every attempt to fix one finding, oldest first."""
        stmt = (
            self._base_select()
            .where(RemediationTask.organization_id == organization_id)
            .where(RemediationTask.finding_id == finding_id)
            .order_by(RemediationTask.created_at, RemediationTask.id)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_filtered(
        self,
        organization_id: UUID,
        *,
        status: RemediationStatus | None = None,
        assignee_id: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[RemediationTask]:
        """Remediation tasks, newest first."""
        stmt = self._base_select().where(RemediationTask.organization_id == organization_id)
        if status is not None:
            stmt = stmt.where(RemediationTask.status == str(status))
        if assignee_id is not None:
            stmt = stmt.where(RemediationTask.assignee_id == assignee_id)
        stmt = (
            stmt.order_by(RemediationTask.created_at.desc(), RemediationTask.id)
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_in_window(
        self, organization_id: UUID, *, since: datetime, until: datetime
    ) -> dict[str, int]:
        """How many remediations landed in each status inside a window."""
        stmt = (
            select(RemediationTask.status, func.count())
            .where(RemediationTask.organization_id == organization_id)
            .where(RemediationTask.created_at >= since)
            .where(RemediationTask.created_at < until)
            .where(RemediationTask.deleted_at.is_(None))
            .group_by(RemediationTask.status)
        )
        rows = (await self._session.execute(stmt)).all()
        return {str(status): int(count) for status, count in rows}


class ScoreRepository(BaseRepository[ComplianceScore]):
    """Computed scores, kept for trending."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ComplianceScore, tenant_scope=tenant_scope)

    async def latest(
        self,
        organization_id: UUID,
        *,
        scope: ScoreScope,
        scope_id: str | None = None,
    ) -> ComplianceScore | None:
        """The most recent score for one scope."""
        stmt = (
            self._base_select()
            .where(ComplianceScore.organization_id == organization_id)
            .where(ComplianceScore.scope == str(scope))
        )
        stmt = (
            stmt.where(ComplianceScore.scope_id.is_(None))
            if scope_id is None
            else stmt.where(ComplianceScore.scope_id == scope_id)
        )
        stmt = stmt.order_by(ComplianceScore.computed_at.desc()).limit(1)
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def history(
        self,
        organization_id: UUID,
        *,
        scope: ScoreScope,
        scope_id: str | None = None,
        since: datetime | None = None,
        limit: int = 365,
    ) -> list[ComplianceScore]:
        """A scope's score over time, oldest first for charting."""
        stmt = (
            self._base_select()
            .where(ComplianceScore.organization_id == organization_id)
            .where(ComplianceScore.scope == str(scope))
        )
        if scope_id is not None:
            stmt = stmt.where(ComplianceScore.scope_id == scope_id)
        if since is not None:
            stmt = stmt.where(ComplianceScore.computed_at >= since)
        stmt = stmt.order_by(ComplianceScore.computed_at).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def latest_per_scope(
        self, organization_id: UUID, *, scope: ScoreScope, limit: int = 200
    ) -> list[ComplianceScore]:
        """The newest score for every scope_id at one scope level."""
        stmt = (
            self._base_select()
            .where(ComplianceScore.organization_id == organization_id)
            .where(ComplianceScore.scope == str(scope))
            .order_by(ComplianceScore.scope_id, ComplianceScore.computed_at.desc())
            .limit(limit * 10)
        )
        rows = list((await self._session.execute(stmt)).scalars().all())
        seen: set[str | None] = set()
        newest: list[ComplianceScore] = []
        for row in rows:
            if row.scope_id in seen:
                continue
            seen.add(row.scope_id)
            newest.append(row)
            if len(newest) >= limit:
                break
        return newest


class StatisticRepository(BaseRepository[ComplianceStatistic]):
    """Rolled-up windows."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ComplianceStatistic, tenant_scope=tenant_scope)

    async def get_window(
        self, organization_id: UUID, *, window_start: datetime
    ) -> ComplianceStatistic | None:
        """One window, so a rollup can be idempotent."""
        stmt = (
            self._base_select()
            .where(ComplianceStatistic.organization_id == organization_id)
            .where(ComplianceStatistic.window_start == window_start)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_recent(
        self, organization_id: UUID, *, limit: int = 100
    ) -> list[ComplianceStatistic]:
        """Recent windows, newest first."""
        stmt = (
            self._base_select()
            .where(ComplianceStatistic.organization_id == organization_id)
            .order_by(ComplianceStatistic.window_start.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class ReportRepository(BaseRepository[ComplianceReport]):
    """Generated documents."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ComplianceReport, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, report_id: UUID) -> ComplianceReport:
        """One report by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(ComplianceReport.organization_id == organization_id)
            .where(ComplianceReport.id == report_id)
        )
        result = await self._session.execute(stmt)
        found: ComplianceReport | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No report with id {report_id} in this organization.")
        return found

    async def list_for_org(
        self, organization_id: UUID, *, limit: int = 100, offset: int = 0
    ) -> list[ComplianceReport]:
        """Reports, newest first."""
        stmt = (
            self._base_select()
            .where(ComplianceReport.organization_id == organization_id)
            .order_by(ComplianceReport.created_at.desc(), ComplianceReport.id)
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class HistoryRepository(BaseRepository[ComplianceHistory]):
    """State over time, for trending and for proof."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ComplianceHistory, tenant_scope=tenant_scope)

    async def list_for_entity(
        self,
        organization_id: UUID,
        *,
        entity_type: str,
        entity_id: UUID | None = None,
        limit: int = 200,
    ) -> list[ComplianceHistory]:
        """One thing's history, newest first."""
        stmt = (
            self._base_select()
            .where(ComplianceHistory.organization_id == organization_id)
            .where(ComplianceHistory.entity_type == entity_type)
        )
        if entity_id is not None:
            stmt = stmt.where(ComplianceHistory.entity_id == entity_id)
        stmt = stmt.order_by(ComplianceHistory.recorded_at.desc()).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class AuditRepository(BaseRepository[ComplianceAudit]):
    """Append-only record of who did what.

    No update method and no delete method, deliberately. An audit trail
    that can be edited is not an audit trail, and the place to prevent
    that is the only code that can reach the table.
    """

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ComplianceAudit, tenant_scope=tenant_scope)

    async def list_for_org(
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
        stmt = self._base_select().where(ComplianceAudit.organization_id == organization_id)
        if entity_type is not None:
            stmt = stmt.where(ComplianceAudit.entity_type == entity_type)
        if entity_id is not None:
            stmt = stmt.where(ComplianceAudit.entity_id == entity_id)
        if actor_id is not None:
            stmt = stmt.where(ComplianceAudit.actor_id == actor_id)
        if since is not None:
            stmt = stmt.where(ComplianceAudit.occurred_at >= since)
        stmt = (
            stmt.order_by(ComplianceAudit.occurred_at.desc(), ComplianceAudit.id)
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_action(self, organization_id: UUID, *, since: datetime) -> dict[str, int]:
        """How many entries of each action since a moment."""
        stmt = (
            select(ComplianceAudit.action, func.count())
            .where(ComplianceAudit.organization_id == organization_id)
            .where(ComplianceAudit.occurred_at >= since)
            .group_by(ComplianceAudit.action)
        )
        rows = (await self._session.execute(stmt)).all()
        return {str(action): int(count) for action, count in rows}


__all__ = [
    "AuditRepository",
    "ExceptionRepository",
    "FindingRepository",
    "HistoryRepository",
    "RemediationRepository",
    "ReportRepository",
    "RiskRepository",
    "ScoreRepository",
    "StatisticRepository",
]
