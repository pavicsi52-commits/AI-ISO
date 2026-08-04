"""Notification CRUD, lifecycle, send, and broadcast (docs/055 "REST APIs")."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status
from shared_core.logging.context import get_log_context

from app.api.deps import AuditSvc, BroadcastSvc, CurrentUserId, DeliverySvc, NotificationSvc
from app.models.enums import AuditAction, NotificationCategory, NotificationStatus
from app.schemas.notification import (
    BroadcastResponse,
    DeliveryResponse,
    NotificationBroadcastRequest,
    NotificationCreateRequest,
    NotificationResponse,
    NotificationSendRequest,
)
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/notifications", tags=["Notifications"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.get("", response_model=SuccessResponse[list[NotificationResponse]], summary="List notifications")
async def list_notifications(
    organization_id: UUID,
    notifications: NotificationSvc,
    user_id: Annotated[str | None, Query()] = None,
    status_filter: Annotated[NotificationStatus | None, Query(alias="status")] = None,
    category: Annotated[NotificationCategory | None, Query()] = None,
    source_service: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=1_000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SuccessResponse[list[NotificationResponse]]:
    """List notifications matching a caller's filters."""
    rows = await notifications.list_notifications(
        organization_id,
        user_id=user_id,
        status=status_filter,
        category=category,
        source_service=source_service,
        limit=limit,
        offset=offset,
    )
    return SuccessResponse(
        message="Notifications listed.",
        data=[NotificationResponse.model_validate(row) for row in rows],
        meta=_meta(),
    )


@router.get(
    "/{notification_id}", response_model=SuccessResponse[NotificationResponse], summary="Get a notification"
)
async def get_notification(
    organization_id: UUID, notification_id: UUID, notifications: NotificationSvc
) -> SuccessResponse[NotificationResponse]:
    """One notification."""
    found = await notifications.get(organization_id, notification_id)
    return SuccessResponse(
        message="Notification found.", data=NotificationResponse.model_validate(found), meta=_meta()
    )


@router.post(
    "",
    response_model=SuccessResponse[NotificationResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create a notification (without dispatching it)",
)
async def create_notification(
    organization_id: UUID,
    body: NotificationCreateRequest,
    notifications: NotificationSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[NotificationResponse]:
    """Create a notification, ``CREATED`` and not yet dispatched."""
    created = await notifications.create(
        organization_id,
        user_id=body.user_id,
        category=body.category,
        priority=body.priority,
        subject=body.subject,
        body=body.body,
        template_id=body.template_id,
        template_variables=body.template_variables,
        source_service=body.source_service,
        source_event_type=body.source_event_type,
        correlation_id=body.correlation_id,
        expires_at=body.expires_at,
        tags=body.tags,
        metadata=body.metadata,
        actor_id=str(caller),
    )
    await audit.record(
        organization_id,
        action=AuditAction.NOTIFICATION_CREATED,
        entity_type="notification",
        entity_id=created.id,
        actor_id=str(caller),
        summary=f"Created a notification for {created.user_id!r}.",
    )
    return SuccessResponse(
        message="Notification created.",
        data=NotificationResponse.model_validate(created),
        meta=_meta(),
    )


@router.delete(
    "/{notification_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a notification"
)
async def delete_notification(
    organization_id: UUID, notification_id: UUID, notifications: NotificationSvc, caller: CurrentUserId
) -> None:
    """Soft-delete a notification."""
    await notifications.delete(organization_id, notification_id, actor_id=str(caller))


@router.post(
    "/send",
    response_model=SuccessResponse[NotificationResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create and immediately dispatch a notification",
)
async def send_notification(
    organization_id: UUID,
    body: NotificationSendRequest,
    notifications: NotificationSvc,
    delivery: DeliverySvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[NotificationResponse]:
    """Create a notification and dispatch it over its resolved channel(s)."""
    created = await notifications.create(
        organization_id,
        user_id=body.user_id,
        category=body.category,
        priority=body.priority,
        subject=body.subject,
        body=body.body,
        template_id=body.template_id,
        template_variables=body.template_variables,
        source_service=body.source_service,
        source_event_type=body.source_event_type,
        correlation_id=body.correlation_id,
        expires_at=body.expires_at,
        tags=body.tags,
        metadata=body.metadata,
        actor_id=str(caller),
    )
    await delivery.dispatch(organization_id, created, requested_channel=body.channel)
    await audit.record(
        organization_id,
        action=AuditAction.NOTIFICATION_SENT,
        entity_type="notification",
        entity_id=created.id,
        actor_id=str(caller),
        summary=f"Sent a notification to {created.user_id!r}.",
    )
    refreshed = await notifications.get(organization_id, created.id)
    return SuccessResponse(
        message="Notification sent.", data=NotificationResponse.model_validate(refreshed), meta=_meta()
    )


@router.post(
    "/broadcast",
    response_model=SuccessResponse[BroadcastResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Fan a notification out to many recipients",
)
async def broadcast_notification(
    organization_id: UUID,
    body: NotificationBroadcastRequest,
    broadcasts: BroadcastSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[BroadcastResponse]:
    """Broadcast a notification to a topic's subscribers and/or an explicit recipient list."""
    created = await broadcasts.broadcast(
        organization_id,
        body=body.body,
        category=body.category,
        priority=body.priority,
        subject=body.subject,
        channel=body.channel,
        topic=body.topic,
        recipient_user_ids=body.recipient_user_ids,
        announcement_id=body.announcement_id,
        initiated_by=str(caller),
    )
    await audit.record(
        organization_id,
        action=AuditAction.BROADCAST_INITIATED,
        entity_type="broadcast",
        entity_id=created.id,
        actor_id=str(caller),
        summary=f"Broadcast to {created.total_recipients} recipient(s).",
    )
    return SuccessResponse(
        message="Broadcast completed.", data=BroadcastResponse.model_validate(created), meta=_meta()
    )


@router.post(
    "/{notification_id}/read",
    response_model=SuccessResponse[NotificationResponse],
    summary="Mark a notification read",
)
async def mark_read(
    organization_id: UUID, notification_id: UUID, notifications: NotificationSvc
) -> SuccessResponse[NotificationResponse]:
    """Mark a notification as read ("Read/Unread")."""
    updated = await notifications.mark_read(organization_id, notification_id)
    return SuccessResponse(
        message="Notification marked read.", data=NotificationResponse.model_validate(updated), meta=_meta()
    )


@router.post(
    "/{notification_id}/acknowledge",
    response_model=SuccessResponse[NotificationResponse],
    summary="Acknowledge a notification",
)
async def acknowledge_notification(
    organization_id: UUID, notification_id: UUID, notifications: NotificationSvc
) -> SuccessResponse[NotificationResponse]:
    """Acknowledge a notification ("Acknowledged")."""
    updated = await notifications.acknowledge(organization_id, notification_id)
    return SuccessResponse(
        message="Notification acknowledged.",
        data=NotificationResponse.model_validate(updated),
        meta=_meta(),
    )


@router.post(
    "/{notification_id}/cancel",
    response_model=SuccessResponse[NotificationResponse],
    summary="Cancel a not-yet-terminal notification",
)
async def cancel_notification(
    organization_id: UUID, notification_id: UUID, notifications: NotificationSvc
) -> SuccessResponse[NotificationResponse]:
    """Cancel a notification that has not reached a terminal state."""
    updated = await notifications.cancel(organization_id, notification_id)
    return SuccessResponse(
        message="Notification cancelled.", data=NotificationResponse.model_validate(updated), meta=_meta()
    )


@router.get(
    "/{notification_id}/deliveries",
    response_model=SuccessResponse[list[DeliveryResponse]],
    summary="List one notification's own deliveries",
)
async def list_notification_deliveries(
    organization_id: UUID, notification_id: UUID, delivery: DeliverySvc
) -> SuccessResponse[list[DeliveryResponse]]:
    """Every channel one notification was (or is being) delivered over."""
    rows = await delivery.list_for_notification(organization_id, notification_id)
    return SuccessResponse(
        message="Deliveries listed.",
        data=[DeliveryResponse.model_validate(row) for row in rows],
        meta=_meta(),
    )


__all__ = ["router"]
