"""Repositories for what the engine produces at runtime.

Decisions, violations, exceptions, approvals, quotas, simulations, and
the operational tables.

**The quota increment is the one thing here that is not ordinary CRUD.**
It is a single atomic UPDATE, and it has to be -- see
:meth:`PolicyQuotaRepository.consume`.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy import and_, desc, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.decision import PolicyDecision, PolicyException, PolicyViolation
from app.models.enums import (
    ApprovalStatus,
    AuditAction,
    PolicyEffect,
    QuotaScope,
    ReportKind,
    ViolationStatus,
)
from app.models.governance import PolicyApproval, PolicyQuota, PolicySimulation
from app.models.operations import PolicyAudit, PolicyReport, PolicyStatistics


class PolicyDecisionRepository(BaseRepository[PolicyDecision]):
    """The decision log."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, PolicyDecision, tenant_scope=tenant_scope)

    async def list_for_org(
        self,
        organization_id: UUID,
        *,
        effect: PolicyEffect | None = None,
        subject_id: str | None = None,
        denied_only: bool = False,
        include_simulated: bool = False,
        limit: int = 200,
    ) -> list[PolicyDecision]:
        """Decisions, most recent first.

        Simulated decisions are excluded by default. A simulation runs
        the real engine, so its rows are otherwise indistinguishable from
        live ones -- and a what-if analysis silently inflating the denial
        rate would make the metric useless exactly when somebody is using
        it to plan a change.
        """
        stmt = self._base_select().where(PolicyDecision.organization_id == organization_id)
        if not include_simulated:
            stmt = stmt.where(PolicyDecision.simulated.is_(False))
        if effect is not None:
            stmt = stmt.where(PolicyDecision.effect == effect)
        if subject_id is not None:
            stmt = stmt.where(PolicyDecision.subject_id == subject_id)
        if denied_only:
            stmt = stmt.where(PolicyDecision.permitted.is_(False))
        stmt = stmt.order_by(desc(PolicyDecision.decided_at)).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_request_id(
        self, organization_id: UUID, request_id: str
    ) -> PolicyDecision | None:
        """The decision behind one caller-supplied correlation id.

        How "I got a 403 and I do not know why" is answered across
        service boundaries.
        """
        stmt = (
            self._base_select()
            .where(PolicyDecision.organization_id == organization_id)
            .where(PolicyDecision.request_id == request_id)
            .order_by(desc(PolicyDecision.decided_at))
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def statistics_for_org(self, organization_id: UUID) -> dict[str, float]:
        """Counts and latency, aggregated in the database.

        Aggregated in SQL rather than by loading rows: the rollup runs
        over every organization, and a tenant with a million decisions
        would otherwise pull a million rows to compute five numbers.
        """
        stmt = (
            select(
                func.count().label("total"),
                func.count().filter(PolicyDecision.permitted.is_(True)).label("allowed"),
                func.count().filter(PolicyDecision.permitted.is_(False)).label("denied"),
                func.avg(PolicyDecision.duration_ms).label("average_ms"),
                func.max(PolicyDecision.duration_ms).label("max_ms"),
            )
            .where(PolicyDecision.organization_id == organization_id)
            .where(PolicyDecision.is_active.is_(True))
            .where(PolicyDecision.simulated.is_(False))
        )
        row = (await self._session.execute(stmt)).one()
        return {
            "total": float(row.total or 0),
            "allowed": float(row.allowed or 0),
            "denied": float(row.denied or 0),
            "average_ms": float(row.average_ms or 0.0),
            "max_ms": float(row.max_ms or 0.0),
        }

    async def percentile_latency(self, organization_id: UUID, *, fraction: float = 0.95) -> float:
        """Latency at a given percentile.

        Reported alongside the mean rather than instead of it: a mean is
        dominated by the fast majority and hides the tail entirely, and
        the tail is what a caller with a request timeout experiences.
        """
        stmt = (
            select(func.percentile_cont(fraction).within_group(PolicyDecision.duration_ms))
            .where(PolicyDecision.organization_id == organization_id)
            .where(PolicyDecision.is_active.is_(True))
            .where(PolicyDecision.simulated.is_(False))
        )
        result = await self._session.execute(stmt)
        return float(result.scalar() or 0.0)

    async def counts_by_effect(self, organization_id: UUID) -> dict[str, int]:
        """How many decisions landed on each effect."""
        stmt = (
            select(PolicyDecision.effect, func.count())
            .where(PolicyDecision.organization_id == organization_id)
            .where(PolicyDecision.is_active.is_(True))
            .where(PolicyDecision.simulated.is_(False))
            .group_by(PolicyDecision.effect)
        )
        result = await self._session.execute(stmt)
        return {str(effect): int(count) for effect, count in result.all()}

    async def purge_older_than(self, organization_id: UUID, *, cutoff: datetime) -> int:
        """Delete decisions past their retention; returns how many."""
        stmt = (
            self._base_select()
            .where(PolicyDecision.organization_id == organization_id)
            .where(PolicyDecision.decided_at < cutoff)
        )
        rows = list((await self._session.execute(stmt)).scalars().all())
        for row in rows:
            await self.purge(row.id)
        return len(rows)


class PolicyViolationRepository(BaseRepository[PolicyViolation]):
    """Recorded breaches."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, PolicyViolation, tenant_scope=tenant_scope)

    async def list_for_org(
        self,
        organization_id: UUID,
        *,
        status: ViolationStatus | None = None,
        severity: str | None = None,
        limit: int = 200,
    ) -> list[PolicyViolation]:
        """Violations, most recent first."""
        stmt = self._base_select().where(PolicyViolation.organization_id == organization_id)
        if status is not None:
            stmt = stmt.where(PolicyViolation.status == status)
        if severity is not None:
            stmt = stmt.where(PolicyViolation.severity == severity)
        stmt = stmt.order_by(desc(PolicyViolation.detected_at)).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def require_by_id(self, organization_id: UUID, violation_id: UUID) -> PolicyViolation:
        """One violation, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(PolicyViolation.organization_id == organization_id)
            .where(PolicyViolation.id == violation_id)
        )
        found = (await self._session.execute(stmt)).scalars().first()
        if found is None:
            raise NotFoundError(f"No violation with id {violation_id} in this organization.")
        return found

    async def count_open(self, organization_id: UUID) -> int:
        """How many violations are still open."""
        stmt = (
            select(func.count())
            .select_from(PolicyViolation)
            .where(PolicyViolation.organization_id == organization_id)
            .where(PolicyViolation.is_active.is_(True))
            .where(PolicyViolation.status == ViolationStatus.OPEN)
        )
        return int((await self._session.execute(stmt)).scalar() or 0)


class PolicyExceptionRepository(BaseRepository[PolicyException]):
    """Scoped, expiring waivers."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, PolicyException, tenant_scope=tenant_scope)

    async def list_active(
        self,
        organization_id: UUID,
        *,
        policy_id: UUID | None = None,
        moment: datetime,
    ) -> list[PolicyException]:
        """Waivers in force right now.

        Filtered on both expiry *and* revocation in the query, never in
        Python afterwards. An expired or revoked exception that reached
        the evaluator would waive a policy that is meant to be back in
        force, which is a grant nobody authorised.
        """
        stmt = (
            self._base_select()
            .where(PolicyException.organization_id == organization_id)
            .where(PolicyException.expires_at > moment)
            .where(PolicyException.revoked_at.is_(None))
        )
        if policy_id is not None:
            stmt = stmt.where(PolicyException.policy_id == policy_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_org(
        self, organization_id: UUID, *, limit: int = 200
    ) -> list[PolicyException]:
        """Every waiver, live or not, newest first."""
        stmt = (
            self._base_select()
            .where(PolicyException.organization_id == organization_id)
            .order_by(desc(PolicyException.granted_at))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def record_use(self, exception_id: UUID) -> None:
        """Count one reliance on a waiver.

        Incremented in the database rather than read-modify-written, for
        the same reason quota consumption is: several requests can rely
        on one waiver concurrently, and a lost update here understates
        exactly the number somebody uses to decide whether the waiver has
        quietly become the real policy.
        """
        await self._session.execute(
            update(PolicyException)
            .where(PolicyException.id == exception_id)
            .values(use_count=PolicyException.use_count + 1)
        )


class PolicyApprovalRepository(BaseRepository[PolicyApproval]):
    """Outstanding obligations."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, PolicyApproval, tenant_scope=tenant_scope)

    async def list_for_org(
        self,
        organization_id: UUID,
        *,
        status: ApprovalStatus | None = None,
        subject_id: str | None = None,
        limit: int = 200,
    ) -> list[PolicyApproval]:
        """Approvals, most recently requested first."""
        stmt = self._base_select().where(PolicyApproval.organization_id == organization_id)
        if status is not None:
            stmt = stmt.where(PolicyApproval.status == status)
        if subject_id is not None:
            stmt = stmt.where(PolicyApproval.subject_id == subject_id)
        stmt = stmt.order_by(desc(PolicyApproval.requested_at)).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def require_by_id(self, organization_id: UUID, approval_id: UUID) -> PolicyApproval:
        """One approval, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(PolicyApproval.organization_id == organization_id)
            .where(PolicyApproval.id == approval_id)
        )
        found = (await self._session.execute(stmt)).scalars().first()
        if found is None:
            raise NotFoundError(f"No approval with id {approval_id} in this organization.")
        return found

    async def list_expired_pending(
        self, organization_id: UUID, *, moment: datetime, limit: int = 500
    ) -> list[PolicyApproval]:
        """Pending approvals whose deadline has passed."""
        stmt = (
            self._base_select()
            .where(PolicyApproval.organization_id == organization_id)
            .where(PolicyApproval.status == ApprovalStatus.PENDING)
            .where(PolicyApproval.expires_at <= moment)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_pending(self, organization_id: UUID) -> int:
        """How many approvals are still waiting."""
        stmt = (
            select(func.count())
            .select_from(PolicyApproval)
            .where(PolicyApproval.organization_id == organization_id)
            .where(PolicyApproval.is_active.is_(True))
            .where(PolicyApproval.status == ApprovalStatus.PENDING)
        )
        return int((await self._session.execute(stmt)).scalar() or 0)


class PolicyQuotaRepository(BaseRepository[PolicyQuota]):
    """Consumption budgets."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, PolicyQuota, tenant_scope=tenant_scope)

    async def list_applicable(
        self,
        organization_id: UUID,
        *,
        scopes: list[tuple[QuotaScope, str]],
        resource: str | None = None,
    ) -> list[PolicyQuota]:
        """Every quota that applies to one request.

        A request is usually inside several budgets at once -- the
        organization's, the project's, and the user's -- so this returns
        all of them and the caller checks against every one. Returning
        only the narrowest would let a user inside their personal limit
        blow through the organization's.
        """
        if not scopes:
            return []
        conditions = [
            and_(PolicyQuota.scope == scope, PolicyQuota.scope_id == scope_id)
            for scope, scope_id in scopes
        ]
        stmt = (
            self._base_select()
            .where(PolicyQuota.organization_id == organization_id)
            .where(or_(*conditions))
        )
        if resource is not None:
            stmt = stmt.where(PolicyQuota.resource == resource)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_one(
        self,
        organization_id: UUID,
        *,
        scope: QuotaScope,
        scope_id: str,
        resource: str,
    ) -> PolicyQuota | None:
        """One quota by its natural key."""
        stmt = (
            self._base_select()
            .where(PolicyQuota.organization_id == organization_id)
            .where(PolicyQuota.scope == scope)
            .where(PolicyQuota.scope_id == scope_id)
            .where(PolicyQuota.resource == resource)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_for_org(self, organization_id: UUID, *, limit: int = 200) -> list[PolicyQuota]:
        """Every quota an organization has defined."""
        stmt = (
            self._base_select()
            .where(PolicyQuota.organization_id == organization_id)
            .order_by(PolicyQuota.scope, PolicyQuota.resource)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def consume(self, quota_id: UUID, amount: float) -> None:
        """Add to a quota's consumption, atomically.

        **A single UPDATE, never a read-modify-write.** Quota enforcement
        runs on the request path across every replica of every service on
        the platform, so two concurrent requests reading 99, each adding
        1, and each writing 100 is not a rare interleaving -- it is the
        normal case under any load worth having a quota for. Every lost
        update is a request that consumed budget without being counted,
        and the drift is silent and permanent.
        """
        await self._session.execute(
            update(PolicyQuota)
            .where(PolicyQuota.id == quota_id)
            .values(consumed=PolicyQuota.consumed + amount)
        )

    async def reset_period(self, quota_id: UUID, *, period_started_at: datetime) -> None:
        """Roll a quota into a new period.

        Consumption and the warning marker both clear: a warning that
        survived the reset would stay silent through the next period's
        approach to the limit, which is the one time it is needed.
        """
        await self._session.execute(
            update(PolicyQuota)
            .where(PolicyQuota.id == quota_id)
            .values(
                consumed=0.0,
                period_started_at=period_started_at,
                warning_sent_at=None,
                exceeded_at=None,
            )
        )

    async def record_exceeded(self, quota_id: UUID, *, moment: datetime) -> None:
        """Mark a quota as having blocked something."""
        await self._session.execute(
            update(PolicyQuota)
            .where(PolicyQuota.id == quota_id)
            .values(exceeded_at=moment, exceeded_count=PolicyQuota.exceeded_count + 1)
        )


class PolicySimulationRepository(BaseRepository[PolicySimulation]):
    """Stored rehearsals."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, PolicySimulation, tenant_scope=tenant_scope)

    async def list_for_org(
        self, organization_id: UUID, *, limit: int = 100
    ) -> list[PolicySimulation]:
        """Simulations, most recent first."""
        stmt = (
            self._base_select()
            .where(PolicySimulation.organization_id == organization_id)
            .order_by(desc(PolicySimulation.started_at))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def require_by_id(self, organization_id: UUID, simulation_id: UUID) -> PolicySimulation:
        """One simulation, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(PolicySimulation.organization_id == organization_id)
            .where(PolicySimulation.id == simulation_id)
        )
        found = (await self._session.execute(stmt)).scalars().first()
        if found is None:
            raise NotFoundError(f"No simulation with id {simulation_id} in this organization.")
        return found


class PolicyStatisticsRepository(BaseRepository[PolicyStatistics]):
    """One rollup row per organization."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, PolicyStatistics, tenant_scope=tenant_scope)

    async def get_for_org(self, organization_id: UUID) -> PolicyStatistics | None:
        """The stored rollup, or ``None``."""
        stmt = self._base_select().where(PolicyStatistics.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return result.scalars().first()


class PolicyReportRepository(BaseRepository[PolicyReport]):
    """Generated reports."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, PolicyReport, tenant_scope=tenant_scope)

    async def list_for_org(
        self, organization_id: UUID, *, kind: ReportKind | None = None, limit: int = 100
    ) -> list[PolicyReport]:
        """Reports, most recent first."""
        stmt = self._base_select().where(PolicyReport.organization_id == organization_id)
        if kind is not None:
            stmt = stmt.where(PolicyReport.kind == kind)
        stmt = stmt.order_by(desc(PolicyReport.generated_at)).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def require_by_id(self, organization_id: UUID, report_id: UUID) -> PolicyReport:
        """One report, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here. A report payload
                can hold every decision an organization has made, so the
                ownership check is the difference between a download and
                a disclosure.
        """
        stmt = (
            self._base_select()
            .where(PolicyReport.organization_id == organization_id)
            .where(PolicyReport.id == report_id)
        )
        found = (await self._session.execute(stmt)).scalars().first()
        if found is None:
            raise NotFoundError(f"No report with id {report_id} in this organization.")
        return found


class PolicyAuditRepository(BaseRepository[PolicyAudit]):
    """The append-only trail."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, PolicyAudit, tenant_scope=tenant_scope)

    async def list_for_org(
        self,
        organization_id: UUID,
        *,
        action: AuditAction | None = None,
        limit: int = 200,
    ) -> list[PolicyAudit]:
        """Audit entries, most recent first."""
        stmt = self._base_select().where(PolicyAudit.organization_id == organization_id)
        if action is not None:
            stmt = stmt.where(PolicyAudit.action == action)
        stmt = stmt.order_by(desc(PolicyAudit.occurred_at)).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_entity(
        self, organization_id: UUID, entity_id: str, *, limit: int = 100
    ) -> list[PolicyAudit]:
        """Everything audited against one entity.

        Scoped to the organization: an entity id is often a slug, and an
        unscoped by-key read lets one tenant read another's trail by
        guessing a name.
        """
        stmt = (
            self._base_select()
            .where(PolicyAudit.organization_id == organization_id)
            .where(PolicyAudit.entity_id == entity_id)
            .order_by(desc(PolicyAudit.occurred_at))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = [
    "PolicyApprovalRepository",
    "PolicyAuditRepository",
    "PolicyDecisionRepository",
    "PolicyExceptionRepository",
    "PolicyQuotaRepository",
    "PolicyReportRepository",
    "PolicySimulationRepository",
    "PolicyStatisticsRepository",
    "PolicyViolationRepository",
]
