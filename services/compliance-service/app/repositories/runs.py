"""Repositories for assessments, scans, results, and evidence.

The read-heavy half of the service. An assessment of two thousand
controls across five thousand hosts writes ten million result rows, so
every list here is paged and ordered -- ``LIMIT`` without ``ORDER BY``
has no defined meaning in SQL, and a paged walk without one can return
the same row twice and miss another entirely.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import ComplianceAssessment, ComplianceResult, ComplianceScan
from app.models.enums import (
    TERMINAL_ASSESSMENT_STATUSES,
    AssessmentStatus,
    ResultStatus,
    ScanStatus,
)
from app.models.evidence import ComplianceEvidence


class AssessmentRepository(BaseRepository[ComplianceAssessment]):
    """Assessment runs."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ComplianceAssessment, tenant_scope=tenant_scope)

    async def require_in_org(
        self, organization_id: UUID, assessment_id: UUID
    ) -> ComplianceAssessment:
        """One assessment by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(ComplianceAssessment.organization_id == organization_id)
            .where(ComplianceAssessment.id == assessment_id)
        )
        result = await self._session.execute(stmt)
        found: ComplianceAssessment | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No assessment with id {assessment_id} in this organization.")
        return found

    async def list_for_org(
        self,
        organization_id: UUID,
        *,
        status: AssessmentStatus | None = None,
        framework_id: UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ComplianceAssessment]:
        """Assessments, newest first."""
        stmt = self._base_select().where(ComplianceAssessment.organization_id == organization_id)
        if status is not None:
            stmt = stmt.where(ComplianceAssessment.status == str(status))
        if framework_id is not None:
            stmt = stmt.where(ComplianceAssessment.framework_id == framework_id)
        stmt = (
            stmt.order_by(ComplianceAssessment.created_at.desc(), ComplianceAssessment.id)
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def latest_completed(
        self, organization_id: UUID, *, framework_id: UUID | None = None
    ) -> ComplianceAssessment | None:
        """The most recent finished run, for comparison and trending."""
        stmt = (
            self._base_select()
            .where(ComplianceAssessment.organization_id == organization_id)
            .where(ComplianceAssessment.status == str(AssessmentStatus.COMPLETED))
        )
        if framework_id is not None:
            stmt = stmt.where(ComplianceAssessment.framework_id == framework_id)
        stmt = stmt.order_by(ComplianceAssessment.completed_at.desc()).limit(1)
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_stuck(
        self, organization_id: UUID, *, older_than: datetime, limit: int = 100
    ) -> list[ComplianceAssessment]:
        """Runs that started and never finished.

        A worker that died mid-assessment leaves a ``RUNNING`` row
        forever. Left alone it blocks the next scheduled run for that
        framework, so the maintenance sweep needs to be able to find it.
        """
        stmt = (
            self._base_select()
            .where(ComplianceAssessment.organization_id == organization_id)
            .where(ComplianceAssessment.status == str(AssessmentStatus.RUNNING))
            .where(ComplianceAssessment.started_at < older_than)
            .order_by(ComplianceAssessment.started_at)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_in_window(
        self, organization_id: UUID, *, since: datetime, until: datetime
    ) -> dict[str, int]:
        """How many runs landed in each status inside a window."""
        stmt = (
            select(ComplianceAssessment.status, func.count())
            .where(ComplianceAssessment.organization_id == organization_id)
            .where(ComplianceAssessment.created_at >= since)
            .where(ComplianceAssessment.created_at < until)
            .where(ComplianceAssessment.deleted_at.is_(None))
            .group_by(ComplianceAssessment.status)
        )
        rows = (await self._session.execute(stmt)).all()
        return {str(status): int(count) for status, count in rows}

    async def has_running(self, organization_id: UUID, *, framework_id: UUID | None) -> bool:
        """Whether a run is already in flight for this framework.

        What stops a continuous schedule from stacking runs on top of
        each other when one takes longer than its interval -- the
        failure mode where a slow assessment makes the estate slower,
        which makes the assessment slower.
        """
        stmt = (
            select(func.count())
            .select_from(ComplianceAssessment)
            .where(ComplianceAssessment.organization_id == organization_id)
            .where(
                ComplianceAssessment.status.notin_(
                    [str(one) for one in TERMINAL_ASSESSMENT_STATUSES]
                )
            )
            .where(ComplianceAssessment.deleted_at.is_(None))
        )
        if framework_id is not None:
            stmt = stmt.where(ComplianceAssessment.framework_id == framework_id)
        return int((await self._session.execute(stmt)).scalar_one()) > 0


class ScanRepository(BaseRepository[ComplianceScan]):
    """Collector passes."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ComplianceScan, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, scan_id: UUID) -> ComplianceScan:
        """One scan by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(ComplianceScan.organization_id == organization_id)
            .where(ComplianceScan.id == scan_id)
        )
        result = await self._session.execute(stmt)
        found: ComplianceScan | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No scan with id {scan_id} in this organization.")
        return found

    async def list_for_org(
        self,
        organization_id: UUID,
        *,
        status: ScanStatus | None = None,
        assessment_id: UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ComplianceScan]:
        """Scans, newest first."""
        stmt = self._base_select().where(ComplianceScan.organization_id == organization_id)
        if status is not None:
            stmt = stmt.where(ComplianceScan.status == str(status))
        if assessment_id is not None:
            stmt = stmt.where(ComplianceScan.assessment_id == assessment_id)
        stmt = (
            stmt.order_by(ComplianceScan.created_at.desc(), ComplianceScan.id)
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_in_window(
        self, organization_id: UUID, *, since: datetime, until: datetime
    ) -> int:
        """How many scans ran inside a window."""
        stmt = (
            select(func.count())
            .select_from(ComplianceScan)
            .where(ComplianceScan.organization_id == organization_id)
            .where(ComplianceScan.created_at >= since)
            .where(ComplianceScan.created_at < until)
            .where(ComplianceScan.deleted_at.is_(None))
        )
        return int((await self._session.execute(stmt)).scalar_one())


class ResultRepository(BaseRepository[ComplianceResult]):
    """Per-control, per-target verdicts."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ComplianceResult, tenant_scope=tenant_scope)

    async def list_for_assessment(
        self,
        organization_id: UUID,
        assessment_id: UUID,
        *,
        status: ResultStatus | None = None,
        limit: int = 5_000,
        offset: int = 0,
    ) -> list[ComplianceResult]:
        """One run's results, paged."""
        stmt = (
            self._base_select()
            .where(ComplianceResult.organization_id == organization_id)
            .where(ComplianceResult.assessment_id == assessment_id)
        )
        if status is not None:
            stmt = stmt.where(ComplianceResult.status == str(status))
        stmt = (
            stmt.order_by(ComplianceResult.control_id, ComplianceResult.id)
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_control(
        self,
        organization_id: UUID,
        control_id: UUID,
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> list[ComplianceResult]:
        """One control's history across runs, newest first."""
        stmt = (
            self._base_select()
            .where(ComplianceResult.organization_id == organization_id)
            .where(ComplianceResult.control_id == control_id)
            .order_by(ComplianceResult.evaluated_at.desc(), ComplianceResult.id)
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_for_assessment(
        self, organization_id: UUID, assessment_id: UUID
    ) -> dict[str, int]:
        """How many results landed in each status, computed in the database.

        Aggregated here rather than by loading rows, because a run of ten
        million results cannot be counted in Python without holding all
        of it in memory -- and the tally is wanted on every dashboard.
        """
        stmt = (
            select(ComplianceResult.status, func.count())
            .where(ComplianceResult.organization_id == organization_id)
            .where(ComplianceResult.assessment_id == assessment_id)
            .where(ComplianceResult.deleted_at.is_(None))
            .group_by(ComplianceResult.status)
        )
        rows = (await self._session.execute(stmt)).all()
        return {str(status): int(count) for status, count in rows}

    async def total_for_assessment(self, organization_id: UUID, assessment_id: UUID) -> int:
        """How many results a run produced, without loading them."""
        stmt = (
            select(func.count())
            .select_from(ComplianceResult)
            .where(ComplianceResult.organization_id == organization_id)
            .where(ComplianceResult.assessment_id == assessment_id)
            .where(ComplianceResult.deleted_at.is_(None))
        )
        return int((await self._session.execute(stmt)).scalar_one())

    async def latest_for_control_target(
        self, organization_id: UUID, control_id: UUID, target_id: str | None
    ) -> ComplianceResult | None:
        """The most recent verdict for one control on one target.

        What remediation verification reads: "does this control pass
        *now*" is a different question from "did the run that raised the
        finding say it passed".
        """
        stmt = (
            self._base_select()
            .where(ComplianceResult.organization_id == organization_id)
            .where(ComplianceResult.control_id == control_id)
        )
        stmt = (
            stmt.where(ComplianceResult.target_id.is_(None))
            if target_id is None
            else stmt.where(ComplianceResult.target_id == target_id)
        )
        stmt = stmt.order_by(ComplianceResult.evaluated_at.desc()).limit(1)
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def count_in_window(
        self, organization_id: UUID, *, since: datetime, until: datetime
    ) -> int:
        """How many controls were evaluated inside a window."""
        stmt = (
            select(func.count())
            .select_from(ComplianceResult)
            .where(ComplianceResult.organization_id == organization_id)
            .where(ComplianceResult.created_at >= since)
            .where(ComplianceResult.created_at < until)
            .where(ComplianceResult.deleted_at.is_(None))
        )
        return int((await self._session.execute(stmt)).scalar_one())


class EvidenceRepository(BaseRepository[ComplianceEvidence]):
    """Immutable proof.

    **This repository has no update method, and that is the point.**
    docs/051 requires immutable evidence, and immutability enforced by
    convention is immutability that lasts until the first person in a
    hurry. Correction goes through :meth:`supersede`, which writes a new
    row and marks the old one -- so both survive and the chain shows
    what was believed and when.
    """

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ComplianceEvidence, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, evidence_id: UUID) -> ComplianceEvidence:
        """One evidence row by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(ComplianceEvidence.organization_id == organization_id)
            .where(ComplianceEvidence.id == evidence_id)
        )
        result = await self._session.execute(stmt)
        found: ComplianceEvidence | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No evidence with id {evidence_id} in this organization.")
        return found

    async def list_for_org(
        self,
        organization_id: UUID,
        *,
        control_id: UUID | None = None,
        assessment_id: UUID | None = None,
        target_id: str | None = None,
        include_superseded: bool = False,
        limit: int = 200,
        offset: int = 0,
    ) -> list[ComplianceEvidence]:
        """Evidence, newest first.

        Superseded rows are excluded by default but never deleted. An
        audit package wants what is current; an investigation into what
        somebody believed last March wants everything, and gets it by
        asking.
        """
        stmt = self._base_select().where(ComplianceEvidence.organization_id == organization_id)
        if control_id is not None:
            stmt = stmt.where(ComplianceEvidence.control_id == control_id)
        if assessment_id is not None:
            stmt = stmt.where(ComplianceEvidence.assessment_id == assessment_id)
        if target_id is not None:
            stmt = stmt.where(ComplianceEvidence.target_id == target_id)
        if not include_superseded:
            stmt = stmt.where(ComplianceEvidence.is_superseded.is_(False))
        stmt = (
            stmt.order_by(ComplianceEvidence.collected_at.desc(), ComplianceEvidence.id)
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def latest_for_target(
        self, organization_id: UUID, target_id: str, *, limit: int = 50
    ) -> list[ComplianceEvidence]:
        """The current evidence for one asset, for an assessment to read."""
        return await self.list_for_org(organization_id, target_id=target_id, limit=limit)

    async def mark_superseded(self, evidence_id: UUID) -> None:
        """Flag one row as replaced.

        The only write this repository makes to an existing evidence
        row, and it touches a flag rather than the payload or the digest
        -- so a verification of the superseded row still succeeds, which
        is what makes the chain provable rather than merely present.
        """
        await self._session.execute(
            update(ComplianceEvidence)
            .where(ComplianceEvidence.id == evidence_id)
            .values(is_superseded=True)
        )

    async def list_expiring(
        self, organization_id: UUID, *, before: datetime, limit: int = 500
    ) -> list[ComplianceEvidence]:
        """Evidence about to stop being current."""
        stmt = (
            self._base_select()
            .where(ComplianceEvidence.organization_id == organization_id)
            .where(ComplianceEvidence.is_superseded.is_(False))
            .where(ComplianceEvidence.expires_at.isnot(None))
            .where(ComplianceEvidence.expires_at <= before)
            .order_by(ComplianceEvidence.expires_at)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_in_window(
        self, organization_id: UUID, *, since: datetime, until: datetime
    ) -> int:
        """How much evidence was collected inside a window."""
        stmt = (
            select(func.count())
            .select_from(ComplianceEvidence)
            .where(ComplianceEvidence.organization_id == organization_id)
            .where(ComplianceEvidence.collected_at >= since)
            .where(ComplianceEvidence.collected_at < until)
            .where(ComplianceEvidence.deleted_at.is_(None))
        )
        return int((await self._session.execute(stmt)).scalar_one())


__all__ = [
    "AssessmentRepository",
    "EvidenceRepository",
    "ResultRepository",
    "ScanRepository",
]
