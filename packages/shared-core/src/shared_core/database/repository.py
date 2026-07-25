"""Generic base repository.

Implements :class:`shared_core.interfaces.RepositoryProtocol` against
SQLAlchemy's async session. Every concrete repository composes this rather
than reimplementing CRUD, per docs/012_Shared_Core_Framework.md.txt
"DATABASE". docs/018_Enterprise_Database_Framework.md.txt "GENERIC
REPOSITORY" adds bulk operations, search, pagination/filtering/sorting, and
tenant-isolation enforcement on top of this -- "No business-specific
repositories" may reimplement any of it.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy import update as sa_update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from shared_core.database.audit import capture_before, record_audit, record_bulk_audit
from shared_core.database.constants import POSTGRES_UNIQUE_VIOLATION
from shared_core.database.exceptions import ConstraintFailedError, DuplicateRecordError
from shared_core.database.filtering import Filter, apply_filters
from shared_core.database.pagination import PaginatedResult, paginate_by_offset
from shared_core.database.search import SearchMode, apply_search
from shared_core.database.soft_delete import mark_deleted, mark_restored
from shared_core.database.soft_delete import purge as purge_entity
from shared_core.database.sorting import SortField, apply_sorting
from shared_core.database.tenant import TenantScope, apply_tenant_scope
from shared_core.database.versioning import check_version, increment_version
from shared_core.enums.audit_action import AuditAction
from shared_core.exceptions.database import DatabaseError
from shared_core.exceptions.not_found import NotFoundError
from shared_core.security.context import get_security_context


def _map_integrity_error(model_name: str, exc: IntegrityError) -> DatabaseError:
    """Map a raw :class:`IntegrityError` to the specific framework exception it represents."""
    sqlstate = getattr(exc.orig, "sqlstate", None) or getattr(exc.orig, "pgcode", None)
    if sqlstate == POSTGRES_UNIQUE_VIOLATION:
        return DuplicateRecordError(f"{model_name} violates a uniqueness constraint.")
    return ConstraintFailedError(f"{model_name} violates a data integrity constraint.")


class BaseRepository[EntityT]:
    """Generic CRUD repository for a SQLAlchemy entity extending
    :class:`shared_core.database.base.BaseModel`.
    """

    def __init__(
        self,
        session: AsyncSession,
        model: type[EntityT],
        *,
        tenant_scope: TenantScope | None = None,
    ) -> None:
        self._session = session
        self._model = model
        self._tenant_scope = tenant_scope

    def _current_actor_id(self) -> UUID | None:
        return get_security_context().user_id

    def _base_select(self, *, include_deleted: bool = False) -> Select[Any]:
        stmt: Select[Any] = select(self._model)
        if not include_deleted:
            stmt = stmt.where(self._model.is_active.is_(True))  # type: ignore[attr-defined]
        if self._tenant_scope is not None:
            stmt = apply_tenant_scope(
                stmt,
                self._model,
                organization_id=self._tenant_scope.organization_id,
                project_id=self._tenant_scope.project_id,
                is_super_admin=self._tenant_scope.is_super_admin,
            )
        return stmt

    async def get_by_id(self, entity_id: UUID, *, include_deleted: bool = False) -> EntityT | None:
        """Return the entity with the given ID, or ``None`` if not found."""
        stmt = self._base_select(include_deleted=include_deleted).where(
            self._model.id == entity_id  # type: ignore[attr-defined]
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    # "Find By ID" and "Find By UUID" (docs/018 "GENERIC REPOSITORY") are the
    # same operation here -- every entity's primary key is already a UUID.
    find_by_id = get_by_id
    find_by_uuid = get_by_id

    async def require_by_id(self, entity_id: UUID) -> EntityT:
        """Return the entity with the given ID, raising if not found."""
        entity = await self.get_by_id(entity_id)
        if entity is None:
            raise NotFoundError(f"{self._model.__name__} '{entity_id}' was not found.")
        return entity

    async def create(self, entity: EntityT, *, actor_id: UUID | None = None) -> EntityT:
        """Persist a new entity and return it."""
        self._session.add(entity)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise _map_integrity_error(self._model.__name__, exc) from exc
        actor = actor_id or self._current_actor_id()
        record_audit(AuditAction.CREATE.value, entity, actor_id=actor)
        return entity

    async def update(
        self,
        entity: EntityT,
        *,
        expected_version: int | None = None,
        actor_id: UUID | None = None,
    ) -> EntityT:
        """Persist changes to an existing entity, enforcing optimistic locking.

        Raises:
            VersionConflictError: If ``expected_version`` is given and does
                not match the entity's current version.
        """
        if expected_version is not None:
            check_version(entity, expected_version)  # type: ignore[arg-type]
        before = capture_before(entity)
        increment_version(entity)  # type: ignore[arg-type]
        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise _map_integrity_error(self._model.__name__, exc) from exc
        record_audit(
            AuditAction.UPDATE.value,
            entity,
            before=before,
            actor_id=actor_id or self._current_actor_id(),
        )
        return entity

    async def delete(self, entity_id: UUID, *, deleted_by: UUID | None = None) -> None:
        """Soft-delete the entity with the given ID."""
        entity = await self.require_by_id(entity_id)
        mark_deleted(entity, deleted_by=deleted_by)  # type: ignore[arg-type]
        await self._session.flush()
        record_audit(
            AuditAction.DELETE.value, entity, actor_id=deleted_by or self._current_actor_id()
        )

    async def restore(self, entity_id: UUID) -> EntityT:
        """Restore a previously soft-deleted entity."""
        entity = await self.get_by_id(entity_id, include_deleted=True)
        if entity is None:
            raise NotFoundError(f"{self._model.__name__} '{entity_id}' was not found.")
        mark_restored(entity)  # type: ignore[arg-type]
        await self._session.flush()
        record_audit(AuditAction.RESTORE.value, entity, actor_id=self._current_actor_id())
        return entity

    async def purge(self, entity_id: UUID) -> None:
        """Permanently remove an entity from the database.

        Reserved for retention-policy cleanup of already soft-deleted
        records (docs/018 "SOFT DELETE": "Purge") -- never a normal
        user-facing delete path.
        """
        entity = await self.get_by_id(entity_id, include_deleted=True)
        if entity is None:
            raise NotFoundError(f"{self._model.__name__} '{entity_id}' was not found.")
        await purge_entity(self._session, entity)

    async def exists(self, entity_id: UUID) -> bool:
        """Return whether an active entity with the given ID exists."""
        return await self.get_by_id(entity_id) is not None

    async def count(self, **filters: Any) -> int:
        """Return the count of active entities matching the given equality filters."""
        stmt = self._base_select()
        for field, value in filters.items():
            stmt = stmt.where(getattr(self._model, field) == value)
        result = await self._session.execute(select(func.count()).select_from(stmt.subquery()))
        return result.scalar_one()

    async def bulk_create(
        self, entities: Sequence[EntityT], *, actor_id: UUID | None = None
    ) -> list[EntityT]:
        """Persist many new entities in one flush."""
        entity_list = list(entities)
        self._session.add_all(entity_list)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise _map_integrity_error(self._model.__name__, exc) from exc
        record_bulk_audit(
            AuditAction.BULK_CREATE.value,
            self._model.__name__,
            count=len(entity_list),
            actor_id=actor_id or self._current_actor_id(),
        )
        return entity_list

    async def bulk_update(
        self, entities: Sequence[EntityT], *, actor_id: UUID | None = None
    ) -> list[EntityT]:
        """Persist changes to many already-loaded entities in one flush.

        Each entity's ``version`` is incremented, exactly as
        :meth:`update` does for a single entity.
        """
        entity_list = list(entities)
        for entity in entity_list:
            increment_version(entity)  # type: ignore[arg-type]
        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise _map_integrity_error(self._model.__name__, exc) from exc
        record_bulk_audit(
            AuditAction.BULK_UPDATE.value,
            self._model.__name__,
            count=len(entity_list),
            actor_id=actor_id or self._current_actor_id(),
        )
        return entity_list

    async def bulk_delete(
        self, entity_ids: Sequence[UUID], *, deleted_by: UUID | None = None
    ) -> int:
        """Soft-delete many entities by ID in a single ``UPDATE`` statement.

        Returns the number of rows actually affected (already-deleted or
        unknown IDs are silently skipped, matching typical bulk-operation
        semantics -- callers wanting "all must exist" should look each one
        up first).
        """
        ids = list(entity_ids)
        if not ids:
            return 0
        stmt = (
            sa_update(self._model)
            .where(self._model.id.in_(ids))  # type: ignore[attr-defined]
            .where(self._model.is_active.is_(True))  # type: ignore[attr-defined]
            .values(deleted_at=datetime.now(UTC), deleted_by=deleted_by, is_active=False)
        )
        result = await self._session.execute(stmt)
        affected = result.rowcount or 0  # type: ignore[attr-defined]
        record_bulk_audit(
            AuditAction.BULK_DELETE.value,
            self._model.__name__,
            count=affected,
            actor_id=deleted_by or self._current_actor_id(),
        )
        return affected

    async def search(
        self,
        fields: Sequence[str],
        query: str,
        *,
        mode: SearchMode = SearchMode.ILIKE,
        include_deleted: bool = False,
    ) -> list[EntityT]:
        """Return active entities matching *query* across *fields*."""
        base_stmt = self._base_select(include_deleted=include_deleted)
        stmt = apply_search(base_stmt, self._model, fields, query, mode=mode)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def paginate(
        self,
        *,
        page: int | None = None,
        page_size: int | None = None,
        filters: Sequence[Filter] | None = None,
        sort_fields: Sequence[SortField] | None = None,
        include_deleted: bool = False,
    ) -> PaginatedResult[EntityT]:
        """Return one page of entities, optionally filtered and sorted."""
        stmt = self._base_select(include_deleted=include_deleted)
        if filters:
            stmt = apply_filters(stmt, self._model, filters)
        if sort_fields:
            stmt = apply_sorting(stmt, self._model, sort_fields)
        return await paginate_by_offset(self._session, stmt, page=page, page_size=page_size)


__all__ = ["BaseRepository"]
