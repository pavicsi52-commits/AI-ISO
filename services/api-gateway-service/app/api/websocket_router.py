"""The WebSocket gateway route.

Authentication is the ``token`` query parameter, not a header, because
browsers cannot set headers on a WebSocket handshake -- the same
constraint ``dashboard-service``'s own WebSocket route documents and
follows. An invalid or missing token closes the socket with
policy-violation ``1008`` rather than serving frames.
"""

from __future__ import annotations

import contextlib
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from shared_core.logging.logger import get_logger
from shared_core.security.jwt import decode_token

from app.websocket.hub import frame_to_text

logger = get_logger("app.api.websocket_router")

router = APIRouter(tags=["WebSocket"])


@router.websocket("/gateway/stream/{organization_id}/ws")
async def gateway_stream(websocket: WebSocket, organization_id: UUID) -> None:
    """Stream this organization's live gateway events."""
    token = websocket.query_params.get("token", "")
    try:
        claims = decode_token(token, public_key=websocket.app.state.jwt_public_key)
        user_id: UUID | None = UUID(str(claims["sub"]))
    except Exception:
        await websocket.close(code=1008, reason="Authentication required.")
        return

    hub = websocket.app.state.websocket_hub
    try:
        subscriber = hub.subscribe(organization_id, user_id=user_id)
    except RuntimeError as exc:
        await websocket.close(code=1013, reason=str(exc))
        return

    await websocket.accept()
    heartbeat = websocket.app.state.service_settings.websocket_heartbeat_seconds
    try:
        async for event in hub.stream(subscriber, heartbeat_seconds=heartbeat):
            await websocket.send_text(frame_to_text(event))
    except WebSocketDisconnect:
        logger.debug(
            "A gateway WebSocket disconnected.",
            extra={"extra_fields": {"organization_id": str(organization_id)}},
        )
    except Exception as exc:
        logger.warning(
            "A gateway WebSocket failed.",
            extra={"extra_fields": {"organization_id": str(organization_id), "error": str(exc)}},
        )
    finally:
        hub.unsubscribe(subscriber)
        with contextlib.suppress(Exception):
            await websocket.close()


__all__ = ["router"]
