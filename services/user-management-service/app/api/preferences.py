"""GET/PUT /users/preferences."""

from __future__ import annotations

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, PreferencesSvc
from app.models.preferences import UserPreferences
from app.schemas.preferences import PreferencesResponse, PreferencesUpdateRequest
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/users/preferences", tags=["Preferences"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def _to_response(preferences: UserPreferences) -> PreferencesResponse:
    return PreferencesResponse(
        user_id=preferences.user_id,
        language=preferences.language,
        theme=preferences.theme,
        timezone=preferences.timezone,
        date_format=preferences.date_format,
        time_format=preferences.time_format,
        dashboard_preferences=preferences.dashboard_preferences,
        notification_preferences=preferences.notification_preferences,
        accessibility=preferences.accessibility,
        default_organization_id=preferences.default_organization_id,
        default_project_id=preferences.default_project_id,
    )


@router.get("", response_model=SuccessResponse[PreferencesResponse])
async def get_preferences(
    preferences: PreferencesSvc, current_user_id: CurrentUserId
) -> SuccessResponse[PreferencesResponse]:
    """Return the caller's own preferences."""
    record = await preferences.get_or_create(current_user_id)
    return SuccessResponse(
        message="Preferences retrieved.", data=_to_response(record), meta=_meta()
    )


@router.put("", response_model=SuccessResponse[PreferencesResponse])
async def update_preferences(
    body: PreferencesUpdateRequest, preferences: PreferencesSvc, current_user_id: CurrentUserId
) -> SuccessResponse[PreferencesResponse]:
    """Update the caller's own preferences ("Preference Changes")."""
    record = await preferences.update(
        current_user_id,
        language=body.language,
        theme=body.theme,
        timezone=body.timezone,
        date_format=body.date_format,
        time_format=body.time_format,
        dashboard_preferences=body.dashboard_preferences,
        notification_preferences=body.notification_preferences,
        accessibility=body.accessibility,
        default_organization_id=body.default_organization_id,
        default_project_id=body.default_project_id,
    )
    return SuccessResponse(message="Preferences updated.", data=_to_response(record), meta=_meta())


__all__ = ["router"]
