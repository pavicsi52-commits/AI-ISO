"""Repository for :class:`app.models.automation_template.AutomationTemplate`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.automation_template import AutomationTemplate
from app.models.enums import PlaybookType


class AutomationTemplateRepository(BaseRepository[AutomationTemplate]):
    """CRUD plus lookup for :class:`AutomationTemplate`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AutomationTemplate, tenant_scope=tenant_scope)

    async def list_for_org(
        self, organization_id: UUID, *, playbook_type: PlaybookType | None = None
    ) -> list[AutomationTemplate]:
        """Every template belonging to *organization_id*, optionally
        narrowed to a single *playbook_type*.
        """
        stmt = self._base_select().where(AutomationTemplate.organization_id == organization_id)
        if playbook_type is not None:
            stmt = stmt.where(AutomationTemplate.playbook_type == playbook_type)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AutomationTemplateRepository"]
