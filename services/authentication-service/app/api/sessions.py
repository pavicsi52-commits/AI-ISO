"""GET/DELETE /auth/sessions{,/{id}}."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.exceptions.not_found import NotFoundError
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUser, SessionSvc
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.session import SessionSummary

router = APIRouter(prefix="/auth/sessions", tags=["Sessions"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.get("", response_model=SuccessResponse[list[SessionSummary]])
async def list_sessions(
    user: CurrentUser, sessions: SessionSvc
) -> SuccessResponse[list[SessionSummary]]:
    """List every active session for the authenticated caller."""
    records = await sessions.list_active(user.id)
    data = [
        SessionSummary(
            id=record.id,
            session_id=record.session_id,
            ip_address=record.ip_address,
            user_agent=record.user_agent,
            created_at=record.created_at,
            last_active_at=record.last_active_at,
            expires_at=record.expires_at,
        )
        for record in records
    ]
    return SuccessResponse(message="Sessions retrieved.", data=data, meta=_meta())


@router.delete("/{session_db_id}", response_model=SuccessResponse[dict[str, bool]])
async def terminate_session(
    session_db_id: UUID, user: CurrentUser, sessions: SessionSvc
) -> SuccessResponse[dict[str, bool]]:
    """Terminate one of the caller's own sessions.

    Raises:
        NotFoundError: If no such session belongs to the caller.
    """
    record = await sessions.get_by_db_id(session_db_id)
    if record is None or record.user_id != user.id:
        raise NotFoundError(f"Session '{session_db_id}' was not found.")
    await sessions.terminate(record.session_id, reason="user_requested")
    return SuccessResponse(message="Session terminated.", data={"success": True}, meta=_meta())


@router.delete("", response_model=SuccessResponse[dict[str, int]])
async def terminate_all_sessions(
    user: CurrentUser, sessions: SessionSvc
) -> SuccessResponse[dict[str, int]]:
    """Terminate every active session for the authenticated caller."""
    count = await sessions.terminate_all_for_user(user.id, reason="user_requested")
    return SuccessResponse(
        message="All sessions terminated.", data={"terminated": count}, meta=_meta()
    )


__all__ = ["router"]
