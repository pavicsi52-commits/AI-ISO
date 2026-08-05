"""Per-organization channel configuration (docs/055 "NOTIFICATION CHANNELS").

A supporting surface, not in docs/055's literal REST API list, but
necessary to actually configure the channels that list names -- the
same "extend the literal API list with the routes its own feature
section requires" precedent every prior AI-IOS service already
establishes.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import AuditSvc, ChannelSvc, CurrentUserId
from app.models.enums import AuditAction, NotificationChannelKind
from app.schemas.notification import ChannelConfigRequest, ChannelConfigResponse
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/notifications/channels", tags=["Channels"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.get(
    "",
    response_model=SuccessResponse[list[ChannelConfigResponse]],
    summary="List configured channels",
)
async def list_channels(
    organization_id: UUID, channels: ChannelSvc
) -> SuccessResponse[list[ChannelConfigResponse]]:
    """Every channel this organization has configured."""
    rows = await channels.list_configs(organization_id)
    return SuccessResponse(
        message="Channels listed.",
        data=[ChannelConfigResponse.model_validate(row) for row in rows],
        meta=_meta(),
    )


@router.put(
    "/{channel}",
    response_model=SuccessResponse[ChannelConfigResponse],
    summary="Configure a channel",
)
async def set_channel(
    organization_id: UUID,
    channel: NotificationChannelKind,
    body: ChannelConfigRequest,
    channels: ChannelSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[ChannelConfigResponse]:
    """Create or replace this organization's configuration for *channel*."""
    updated = await channels.set_config(
        organization_id,
        channel,
        enabled=body.enabled,
        config=body.config,
        description=body.description,
    )
    await audit.record(
        organization_id,
        action=AuditAction.CHANNEL_CONFIGURED,
        entity_type="channel",
        entity_id=updated.id,
        actor_id=str(caller),
        summary=f"Configured channel {channel!s}.",
    )
    return SuccessResponse(
        message="Channel configured.",
        data=ChannelConfigResponse.model_validate(updated),
        meta=_meta(),
    )


__all__ = ["router"]
