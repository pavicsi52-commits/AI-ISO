"""Repositories for implementation tasks, runs, validations, and rollbacks."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.implementation import (
    ChangeImplementation,
    ChangeRollback,
    ChangeTask,
    ChangeValidation,
)


class ChangeTaskRepository(BaseRepository[ChangeTask]):
    """Individual implementation work items."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ChangeTask, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, task_id: UUID) -> ChangeTask:
        """One task by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(ChangeTask.organization_id == organization_id)
            .where(ChangeTask.id == task_id)
        )
        result = await self._session.execute(stmt)
        found: ChangeTask | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No task with id {task_id} in this organization.")
        return found

    async def list_for_change(self, organization_id: UUID, change_id: UUID) -> list[ChangeTask]:
        """Every task for one change, in execution order."""
        stmt = (
            self._base_select()
            .where(ChangeTask.organization_id == organization_id)
            .where(ChangeTask.change_id == change_id)
            .order_by(ChangeTask.sequence)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class ChangeImplementationRepository(BaseRepository[ChangeImplementation]):
    """Implementation runs, as a whole."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ChangeImplementation, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, run_id: UUID) -> ChangeImplementation:
        """One implementation run by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(ChangeImplementation.organization_id == organization_id)
            .where(ChangeImplementation.id == run_id)
        )
        result = await self._session.execute(stmt)
        found: ChangeImplementation | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No implementation run with id {run_id} in this organization.")
        return found

    async def get_for_change(
        self, organization_id: UUID, change_id: UUID
    ) -> ChangeImplementation | None:
        """The (at most one, currently active) implementation run for a change."""
        stmt = (
            self._base_select()
            .where(ChangeImplementation.organization_id == organization_id)
            .where(ChangeImplementation.change_id == change_id)
            .order_by(ChangeImplementation.created_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()


class ChangeValidationRepository(BaseRepository[ChangeValidation]):
    """Validation runs against a change."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ChangeValidation, tenant_scope=tenant_scope)

    async def list_for_change(
        self, organization_id: UUID, change_id: UUID
    ) -> list[ChangeValidation]:
        """Every validation run for one change, oldest first."""
        stmt = (
            self._base_select()
            .where(ChangeValidation.organization_id == organization_id)
            .where(ChangeValidation.change_id == change_id)
            .order_by(ChangeValidation.ran_at)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class ChangeRollbackRepository(BaseRepository[ChangeRollback]):
    """Rollbacks -- undoing a change that did not hold."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ChangeRollback, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, rollback_id: UUID) -> ChangeRollback:
        """One rollback by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(ChangeRollback.organization_id == organization_id)
            .where(ChangeRollback.id == rollback_id)
        )
        result = await self._session.execute(stmt)
        found: ChangeRollback | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No rollback with id {rollback_id} in this organization.")
        return found

    async def list_for_change(self, organization_id: UUID, change_id: UUID) -> list[ChangeRollback]:
        """Every rollback attempt for one change."""
        stmt = (
            self._base_select()
            .where(ChangeRollback.organization_id == organization_id)
            .where(ChangeRollback.change_id == change_id)
            .order_by(ChangeRollback.created_at)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = [
    "ChangeImplementationRepository",
    "ChangeRollbackRepository",
    "ChangeTaskRepository",
    "ChangeValidationRepository",
]
