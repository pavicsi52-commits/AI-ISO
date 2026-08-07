"""Repository for :class:`app.models.session.AgentSession`."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import SessionStatus
from app.models.session import AgentSession


class AgentSessionRepository(BaseRepository[AgentSession]):
    """CRUD plus lookup for :class:`AgentSession`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AgentSession, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, session_id: UUID) -> AgentSession:
        """Return *session_id*, scoped to *organization_id*.

        Raises:
            NotFoundError: If no such session exists in that organization.
        """
        stmt = self._base_select().where(
            AgentSession.id == session_id, AgentSession.organization_id == organization_id
        )
        result = await self._session.execute(stmt)
        found = result.scalars().first()
        if found is None:
            raise NotFoundError(
                f"AgentSession {session_id!s} was not found in organization {organization_id!s}."
            )
        return found

    async def list_active_for_agent(self, agent_id: UUID) -> list[AgentSession]:
        """Every currently-active session for *agent_id*."""
        stmt = self._base_select().where(
            AgentSession.agent_id == agent_id, AgentSession.status == SessionStatus.ACTIVE
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_idle_since(self, cutoff: datetime) -> list[AgentSession]:
        """Every session still ``ACTIVE``/``IDLE`` whose own
        ``last_active_at`` is at or before *cutoff* -- backs the idle-
        session sweep worker.
        """
        stmt = self._base_select().where(
            AgentSession.status.in_((SessionStatus.ACTIVE, SessionStatus.IDLE)),
            AgentSession.last_active_at <= cutoff,
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AgentSessionRepository"]
