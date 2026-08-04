"""Announcement management (docs/055 "ANNOUNCEMENTS")."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status
from shared_core.logging.context import get_log_context

from app.api.deps import AnnouncementSvc, AuditSvc, BroadcastSvc, CurrentUserId
from app.models.enums import AnnouncementStatus, AuditAction
from app.schemas.notification import (
    AnnouncementCreateRequest,
    AnnouncementResponse,
    AnnouncementUpdateRequest,
    BroadcastResponse,
)
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/notifications/announcements", tags=["Announcements"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.get("", response_model=SuccessResponse[list[AnnouncementResponse]], summary="List announcements")
async def list_announcements(
    organization_id: UUID,
    announcements: AnnouncementSvc,
    status_filter: Annotated[AnnouncementStatus | None, Query(alias="status")] = None,
) -> SuccessResponse[list[AnnouncementResponse]]:
    """Announcements in this organization, pinned first."""
    rows = await announcements.list_announcements(organization_id, status=status_filter)
    return SuccessResponse(
        message="Announcements listed.",
        data=[AnnouncementResponse.model_validate(row) for row in rows],
        meta=_meta(),
    )


@router.get(
    "/{announcement_id}", response_model=SuccessResponse[AnnouncementResponse], summary="Get an announcement"
)
async def get_announcement(
    organization_id: UUID, announcement_id: UUID, announcements: AnnouncementSvc
) -> SuccessResponse[AnnouncementResponse]:
    """One announcement."""
    found = await announcements.get(organization_id, announcement_id)
    return SuccessResponse(
        message="Announcement found.", data=AnnouncementResponse.model_validate(found), meta=_meta()
    )


@router.post(
    "",
    response_model=SuccessResponse[AnnouncementResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Draft a new announcement",
)
async def create_announcement(
    organization_id: UUID,
    body: AnnouncementCreateRequest,
    announcements: AnnouncementSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[AnnouncementResponse]:
    """Draft a new announcement -- not yet visible until published."""
    created = await announcements.create(
        organization_id,
        scope=body.scope,
        title=body.title,
        body=body.body,
        is_pinned=body.is_pinned,
        starts_at=body.starts_at,
        expires_at=body.expires_at,
        audience=body.audience,
        actor_id=str(caller),
    )
    await audit.record(
        organization_id,
        action=AuditAction.ANNOUNCEMENT_UPDATED,
        entity_type="announcement",
        entity_id=created.id,
        actor_id=str(caller),
        summary=f"Drafted announcement {created.title!r}.",
    )
    return SuccessResponse(
        message="Announcement drafted.", data=AnnouncementResponse.model_validate(created), meta=_meta()
    )


@router.put(
    "/{announcement_id}",
    response_model=SuccessResponse[AnnouncementResponse],
    summary="Update an announcement",
)
async def update_announcement(
    organization_id: UUID,
    announcement_id: UUID,
    body: AnnouncementUpdateRequest,
    announcements: AnnouncementSvc,
    caller: CurrentUserId,
) -> SuccessResponse[AnnouncementResponse]:
    """Edit a draft announcement's editable fields."""
    updated = await announcements.update(
        organization_id,
        announcement_id,
        actor_id=str(caller),
        title=body.title,
        body=body.body,
        is_pinned=body.is_pinned,
        starts_at=body.starts_at,
        expires_at=body.expires_at,
        audience=body.audience,
    )
    return SuccessResponse(
        message="Announcement updated.", data=AnnouncementResponse.model_validate(updated), meta=_meta()
    )


@router.post(
    "/{announcement_id}/publish",
    response_model=SuccessResponse[AnnouncementResponse],
    summary="Publish an announcement",
)
async def publish_announcement(
    organization_id: UUID,
    announcement_id: UUID,
    announcements: AnnouncementSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[AnnouncementResponse]:
    """Publish an announcement, making it visible to its audience."""
    updated = await announcements.publish(organization_id, announcement_id, actor_id=str(caller))
    await audit.record(
        organization_id,
        action=AuditAction.ANNOUNCEMENT_PUBLISHED,
        entity_type="announcement",
        entity_id=updated.id,
        actor_id=str(caller),
        summary=f"Published announcement {updated.title!r}.",
    )
    return SuccessResponse(
        message="Announcement published.", data=AnnouncementResponse.model_validate(updated), meta=_meta()
    )


@router.post(
    "/{announcement_id}/broadcast",
    response_model=SuccessResponse[BroadcastResponse],
    summary="Fan a published announcement out to its topic subscribers",
)
async def broadcast_announcement(
    organization_id: UUID,
    announcement_id: UUID,
    topic: str,
    announcements: AnnouncementSvc,
    broadcasts: BroadcastSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[BroadcastResponse]:
    """Fan a published announcement out to *topic*'s subscribers."""
    announcement = await announcements.get(organization_id, announcement_id)
    created = await broadcasts.broadcast(
        organization_id,
        body=announcement.body,
        subject=announcement.title,
        topic=topic,
        announcement_id=announcement.id,
        initiated_by=str(caller),
    )
    await audit.record(
        organization_id,
        action=AuditAction.BROADCAST_INITIATED,
        entity_type="broadcast",
        entity_id=created.id,
        actor_id=str(caller),
        summary=f"Broadcast announcement {announcement.title!r} to {created.total_recipients} recipient(s).",
    )
    return SuccessResponse(
        message="Announcement broadcast.", data=BroadcastResponse.model_validate(created), meta=_meta()
    )


@router.post(
    "/{announcement_id}/archive",
    response_model=SuccessResponse[AnnouncementResponse],
    summary="Archive an announcement",
)
async def archive_announcement(
    organization_id: UUID, announcement_id: UUID, announcements: AnnouncementSvc, caller: CurrentUserId
) -> SuccessResponse[AnnouncementResponse]:
    """Archive an announcement, removing it from the active feed."""
    updated = await announcements.archive(organization_id, announcement_id, actor_id=str(caller))
    return SuccessResponse(
        message="Announcement archived.", data=AnnouncementResponse.model_validate(updated), meta=_meta()
    )


__all__ = ["router"]
