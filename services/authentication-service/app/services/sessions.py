"""Session lifecycle.

Per docs/030 "SESSION MANAGEMENT": Create Session, Refresh Session,
Terminate Session, Terminate All Sessions, Idle Timeout, Absolute
Timeout, Concurrent Session Limit, Session Audit.
:class:`shared_core.security.sessions.SessionManager` (Redis) is the
fast, per-request source of truth for "is this session currently
valid"; :class:`app.repositories.session.SessionRepository` (Postgres)
is the durable, listable/auditable record ("GET /auth/sessions",
"DELETE /auth/sessions").
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from shared_core.security.sessions import SessionManager

from app.constants import DEFAULT_ORGANIZATION_ID
from app.models.session import Session
from app.repositories.session import SessionRepository


class SessionService:
    """Creates, validates, refreshes, and terminates user sessions."""

    def __init__(
        self,
        sessions: SessionRepository,
        manager: SessionManager,
        *,
        absolute_timeout_seconds: int,
    ) -> None:
        self._sessions = sessions
        self._manager = manager
        self._absolute_timeout_seconds = absolute_timeout_seconds

    async def create(
        self,
        user_id: UUID,
        *,
        device_id: UUID | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> Session:
        """Create a new session, tracked in both Redis and Postgres ("Create Session")."""
        redis_session = await self._manager.create_session(
            user_id=str(user_id),
            device_id=str(device_id) if device_id is not None else None,
            ip_address=ip_address,
        )
        now = datetime.now(UTC)
        record = Session(
            user_id=user_id,
            session_id=redis_session.session_id,
            device_id=device_id,
            ip_address=ip_address,
            user_agent=user_agent,
            last_active_at=now,
            expires_at=now + timedelta(seconds=self._absolute_timeout_seconds),
            organization_id=DEFAULT_ORGANIZATION_ID,
        )
        return await self._sessions.create(record)

    async def is_valid(self, session_id: str) -> bool:
        """Whether *session_id* is currently valid ("Idle Timeout"/"Absolute Timeout")."""
        return await self._manager.validate_session(session_id) is not None

    async def get_by_db_id(self, session_db_id: UUID) -> Session | None:
        """Return the session row with primary key *session_db_id*, or ``None``."""
        return await self._sessions.get_by_id(session_db_id)

    async def refresh(self, session_id: str) -> None:
        """Extend *session_id*'s idle timeout ("Refresh Session")."""
        refreshed = await self._manager.refresh_session(session_id)
        if refreshed is None:
            return
        record = await self._sessions.get_by_session_id(session_id)
        if record is not None:
            record.last_active_at = refreshed.last_active_at

    async def terminate(self, session_id: str, *, reason: str = "user_requested") -> None:
        """Terminate one session ("Terminate Session")."""
        await self._manager.terminate_session(session_id)
        record = await self._sessions.get_by_session_id(session_id)
        if record is not None and record.revoked_at is None:
            record.revoked_at = datetime.now(UTC)
            record.revoked_reason = reason

    async def terminate_all_for_user(self, user_id: UUID, *, reason: str = "user_requested") -> int:
        """Terminate every active session of *user_id* ("Terminate All Sessions")."""
        records = await self._sessions.list_active_for_user(user_id)
        now = datetime.now(UTC)
        for record in records:
            await self._manager.terminate_session(record.session_id)
            record.revoked_at = now
            record.revoked_reason = reason
        return len(records)

    async def list_active(self, user_id: UUID) -> list[Session]:
        """Every active session for *user_id* ("Session Audit")."""
        return await self._sessions.list_active_for_user(user_id)


__all__ = ["SessionService"]
