"""Repositories for the framework and control catalogue.

Every read is scoped by ``organization_id``, including the ones keyed by
slug or code. A control code is a published identifier -- ``AC-6``,
``A.8.2`` -- so an unscoped lookup by code lets one tenant read another's
compliance posture by guessing a name that is printed in a public
standard. That is not a hard guess.

``require_in_org`` is named differently from the base repository's
unscoped ``require_by_id`` on purpose: two same-named methods of
different arity on one class make an unscoped call look correct, which
is exactly how a cross-tenant read gets written.
"""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ControlCategory, ControlSeverity, ControlStatus, FrameworkStatus
from app.models.framework import ComplianceControl, ComplianceFramework, ControlMapping


class FrameworkRepository(BaseRepository[ComplianceFramework]):
    """The frameworks an organization tracks."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ComplianceFramework, tenant_scope=tenant_scope)

    async def get_by_slug(self, organization_id: UUID, slug: str) -> ComplianceFramework | None:
        """One framework by its slug within an organization."""
        stmt = (
            self._base_select()
            .where(ComplianceFramework.organization_id == organization_id)
            .where(ComplianceFramework.slug == slug)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def require_in_org(
        self, organization_id: UUID, framework_id: UUID
    ) -> ComplianceFramework:
        """One framework by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here. Deliberately not a
                permission error -- telling a caller it exists but
                belongs to someone else confirms the id, which is the one
                thing they did not already know.
        """
        stmt = (
            self._base_select()
            .where(ComplianceFramework.organization_id == organization_id)
            .where(ComplianceFramework.id == framework_id)
        )
        result = await self._session.execute(stmt)
        found: ComplianceFramework | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No framework with id {framework_id} in this organization.")
        return found

    async def list_for_org(
        self,
        organization_id: UUID,
        *,
        status: FrameworkStatus | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[ComplianceFramework]:
        """Frameworks, newest first."""
        stmt = self._base_select().where(ComplianceFramework.organization_id == organization_id)
        if status is not None:
            stmt = stmt.where(ComplianceFramework.status == str(status))
        stmt = (
            stmt.order_by(ComplianceFramework.created_at.desc(), ComplianceFramework.id)
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_active(
        self, organization_id: UUID, *, limit: int = 200
    ) -> list[ComplianceFramework]:
        """Only the frameworks that count toward scores."""
        return await self.list_for_org(organization_id, status=FrameworkStatus.ACTIVE, limit=limit)

    async def refresh_control_count(self, organization_id: UUID, framework_id: UUID) -> int:
        """Recount a framework's controls and store the total.

        Recounted rather than incremented. An increment is wrong the
        first time a control is deleted outside this method, and a stale
        denominator silently changes every score derived from it.
        """
        stmt = (
            select(func.count())
            .select_from(ComplianceControl)
            .where(ComplianceControl.organization_id == organization_id)
            .where(ComplianceControl.framework_id == framework_id)
            .where(ComplianceControl.deleted_at.is_(None))
        )
        total = int((await self._session.execute(stmt)).scalar_one())
        framework = await self.require_in_org(organization_id, framework_id)
        framework.control_count = total
        await self._session.flush()
        return total


class ControlRepository(BaseRepository[ComplianceControl]):
    """The controls inside those frameworks."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ComplianceControl, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, control_id: UUID) -> ComplianceControl:
        """One control by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(ComplianceControl.organization_id == organization_id)
            .where(ComplianceControl.id == control_id)
        )
        result = await self._session.execute(stmt)
        found: ComplianceControl | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No control with id {control_id} in this organization.")
        return found

    async def get_by_code(
        self, organization_id: UUID, framework_id: UUID, code: str
    ) -> ComplianceControl | None:
        """One control by the code its standard uses."""
        stmt = (
            self._base_select()
            .where(ComplianceControl.organization_id == organization_id)
            .where(ComplianceControl.framework_id == framework_id)
            .where(ComplianceControl.code == code)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_for_framework(
        self,
        organization_id: UUID,
        framework_id: UUID,
        *,
        limit: int = 2_000,
        offset: int = 0,
    ) -> list[ComplianceControl]:
        """Every control in one framework, in code order."""
        stmt = (
            self._base_select()
            .where(ComplianceControl.organization_id == organization_id)
            .where(ComplianceControl.framework_id == framework_id)
            .order_by(ComplianceControl.code, ComplianceControl.id)
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_assessable(
        self,
        organization_id: UUID,
        *,
        framework_ids: list[UUID] | None = None,
        automatable_only: bool = True,
        limit: int = 2_000,
    ) -> list[ComplianceControl]:
        """Controls an assessment run should consider.

        ``NOT_APPLICABLE`` controls are **included** rather than filtered
        out, deliberately: the engine needs to emit an explicit
        ``NOT_APPLICABLE`` result for each so that coverage arithmetic
        can tell "we decided this does not apply" from "we never looked
        at this". Filtering here would make the two indistinguishable
        downstream.
        """
        stmt = self._base_select().where(ComplianceControl.organization_id == organization_id)
        if framework_ids:
            stmt = stmt.where(ComplianceControl.framework_id.in_(framework_ids))
        if automatable_only:
            stmt = stmt.where(ComplianceControl.is_automatable.is_(True))
        stmt = stmt.order_by(ComplianceControl.code, ComplianceControl.id).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_filtered(
        self,
        organization_id: UUID,
        *,
        framework_id: UUID | None = None,
        category: ControlCategory | None = None,
        severity: ControlSeverity | None = None,
        status: ControlStatus | None = None,
        owner_id: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[ComplianceControl]:
        """Controls matching a caller's filters."""
        stmt = self._base_select().where(ComplianceControl.organization_id == organization_id)
        if framework_id is not None:
            stmt = stmt.where(ComplianceControl.framework_id == framework_id)
        if category is not None:
            stmt = stmt.where(ComplianceControl.category == str(category))
        if severity is not None:
            stmt = stmt.where(ComplianceControl.severity == str(severity))
        if status is not None:
            stmt = stmt.where(ComplianceControl.status == str(status))
        if owner_id is not None:
            stmt = stmt.where(ComplianceControl.owner_id == owner_id)
        stmt = (
            stmt.order_by(ComplianceControl.code, ComplianceControl.id).offset(offset).limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_status(self, organization_id: UUID) -> dict[str, int]:
        """How many controls sit in each implementation status."""
        stmt = (
            select(ComplianceControl.status, func.count())
            .where(ComplianceControl.organization_id == organization_id)
            .where(ComplianceControl.deleted_at.is_(None))
            .group_by(ComplianceControl.status)
        )
        rows = (await self._session.execute(stmt)).all()
        return {str(status): int(count) for status, count in rows}

    async def list_by_ids(
        self, organization_id: UUID, control_ids: list[UUID]
    ) -> list[ComplianceControl]:
        """Several controls at once, still tenant-scoped."""
        if not control_ids:
            return []
        stmt = (
            self._base_select()
            .where(ComplianceControl.organization_id == organization_id)
            .where(ComplianceControl.id.in_(control_ids))
            .order_by(ComplianceControl.code)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class ControlMappingRepository(BaseRepository[ControlMapping]):
    """How controls relate across frameworks."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ControlMapping, tenant_scope=tenant_scope)

    async def list_for_control(
        self, organization_id: UUID, control_id: UUID
    ) -> list[ControlMapping]:
        """Every mapping touching one control, in either direction.

        Both directions, because a mapping is a statement about a pair
        and a caller asking "what else does this answer?" does not know
        or care which side it was authored from.
        """
        stmt = (
            self._base_select()
            .where(ControlMapping.organization_id == organization_id)
            .where(
                (ControlMapping.source_control_id == control_id)
                | (ControlMapping.target_control_id == control_id)
            )
            .order_by(ControlMapping.created_at, ControlMapping.id)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_pair(
        self, organization_id: UUID, source_control_id: UUID, target_control_id: UUID
    ) -> ControlMapping | None:
        """One directed mapping, if it exists."""
        stmt = (
            self._base_select()
            .where(ControlMapping.organization_id == organization_id)
            .where(ControlMapping.source_control_id == source_control_id)
            .where(ControlMapping.target_control_id == target_control_id)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_for_org(
        self, organization_id: UUID, *, limit: int = 1_000, offset: int = 0
    ) -> list[ControlMapping]:
        """Every mapping an organization has."""
        stmt = (
            self._base_select()
            .where(ControlMapping.organization_id == organization_id)
            .order_by(ControlMapping.created_at, ControlMapping.id)
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["ControlMappingRepository", "ControlRepository", "FrameworkRepository"]
