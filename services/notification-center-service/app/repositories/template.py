"""The notification template and template version repositories."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.template import NotificationTemplate, NotificationTemplateVersion


class NotificationTemplateRepository(BaseRepository[NotificationTemplate]):
    """The template catalogue."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, NotificationTemplate, tenant_scope=tenant_scope)

    async def require_in_org(
        self, organization_id: UUID, template_id: UUID
    ) -> NotificationTemplate:
        """One template by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(NotificationTemplate.organization_id == organization_id)
            .where(NotificationTemplate.id == template_id)
        )
        result = await self._session.execute(stmt)
        found: NotificationTemplate | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No template with id {template_id} in this organization.")
        return found

    async def get_by_key(
        self, organization_id: UUID, template_key: str, *, locale: str = "en"
    ) -> NotificationTemplate | None:
        """The active template for *template_key*/*locale*, if any."""
        stmt = (
            self._base_select()
            .where(NotificationTemplate.organization_id == organization_id)
            .where(NotificationTemplate.template_key == template_key)
            .where(NotificationTemplate.locale == locale)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_for_org(
        self, organization_id: UUID, *, is_active: bool | None = None, limit: int = 500
    ) -> list[NotificationTemplate]:
        """Templates registered in this organization."""
        stmt = self._base_select().where(NotificationTemplate.organization_id == organization_id)
        if is_active is not None:
            stmt = stmt.where(NotificationTemplate.is_active.is_(is_active))
        stmt = stmt.order_by(NotificationTemplate.template_key).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class NotificationTemplateVersionRepository(BaseRepository[NotificationTemplateVersion]):
    """The immutable history of every prior template version."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, NotificationTemplateVersion, tenant_scope=tenant_scope)

    async def list_for_template(
        self, organization_id: UUID, template_id: UUID
    ) -> list[NotificationTemplateVersion]:
        """Every retained version of one template, oldest first."""
        stmt = (
            self._base_select()
            .where(NotificationTemplateVersion.organization_id == organization_id)
            .where(NotificationTemplateVersion.template_id == template_id)
            .order_by(NotificationTemplateVersion.version)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_version(
        self, organization_id: UUID, template_id: UUID, version: int
    ) -> NotificationTemplateVersion | None:
        """One specific version of one template, if retained."""
        stmt = (
            self._base_select()
            .where(NotificationTemplateVersion.organization_id == organization_id)
            .where(NotificationTemplateVersion.template_id == template_id)
            .where(NotificationTemplateVersion.version == version)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()


__all__ = ["NotificationTemplateRepository", "NotificationTemplateVersionRepository"]
