"""The caller's own notification preferences (docs/055 "USER PREFERENCES")."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import AuditSvc, CurrentUserId, PreferenceSvc
from app.models.enums import AuditAction
from app.schemas.notification import PreferenceResponse, PreferenceUpdateRequest
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/notifications/preferences", tags=["Preferences"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.get(
    "",
    response_model=SuccessResponse[PreferenceResponse],
    summary="Get the caller's own preferences",
)
async def get_preferences(
    organization_id: UUID, preferences: PreferenceSvc, caller: CurrentUserId
) -> SuccessResponse[PreferenceResponse]:
    """The calling user's own notification preferences, created permissively if never set."""
    stored = await preferences.get(organization_id, str(caller))
    return SuccessResponse(
        message="Preferences found.", data=PreferenceResponse.model_validate(stored), meta=_meta()
    )


@router.put(
    "",
    response_model=SuccessResponse[PreferenceResponse],
    summary="Update the caller's own preferences",
)
async def update_preferences(
    organization_id: UUID,
    body: PreferenceUpdateRequest,
    preferences: PreferenceSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[PreferenceResponse]:
    """Edit the calling user's own preference fields."""
    updated = await preferences.update(
        organization_id,
        str(caller),
        actor_id=str(caller),
        preferred_channels=body.preferred_channels,
        muted_categories=body.muted_categories,
        unsubscribed_channels=body.unsubscribed_channels,
        channel_priority=body.channel_priority,
        device_tokens=body.device_tokens,
        quiet_hours_start=body.quiet_hours_start,
        quiet_hours_end=body.quiet_hours_end,
        language=body.language,
        timezone=body.timezone,
        digest_frequency=body.digest_frequency,
        muted=body.muted,
        priority_overrides=body.priority_overrides,
    )
    await audit.record(
        organization_id,
        action=AuditAction.PREFERENCE_UPDATED,
        entity_type="preference",
        entity_id=updated.id,
        actor_id=str(caller),
        summary=f"Updated preferences for {caller!s}.",
    )
    return SuccessResponse(
        message="Preferences updated.",
        data=PreferenceResponse.model_validate(updated),
        meta=_meta(),
    )


__all__ = ["router"]
