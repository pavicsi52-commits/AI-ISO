"""GET/PUT /users/settings."""

from __future__ import annotations

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, SettingsSvc
from app.models.settings import UserSettings
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.settings import SettingsResponse, SettingsUpdateRequest

router = APIRouter(prefix="/users/settings", tags=["Settings"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def _to_response(settings: UserSettings) -> SettingsResponse:
    return SettingsResponse(
        user_id=settings.user_id,
        display_settings=settings.display_settings,
        privacy=settings.privacy,
        security_preferences=settings.security_preferences,
        default_views=settings.default_views,
        shortcuts=settings.shortcuts,
        favorites=settings.favorites,
        feature_flags=settings.feature_flags,
    )


@router.get("", response_model=SuccessResponse[SettingsResponse])
async def get_settings_endpoint(
    settings: SettingsSvc, current_user_id: CurrentUserId
) -> SuccessResponse[SettingsResponse]:
    """Return the caller's own settings."""
    record = await settings.get_or_create(current_user_id)
    return SuccessResponse(message="Settings retrieved.", data=_to_response(record), meta=_meta())


@router.put("", response_model=SuccessResponse[SettingsResponse])
async def update_settings(
    body: SettingsUpdateRequest, settings: SettingsSvc, current_user_id: CurrentUserId
) -> SuccessResponse[SettingsResponse]:
    """Update the caller's own settings."""
    record = await settings.update(
        current_user_id,
        display_settings=body.display_settings,
        privacy=body.privacy,
        security_preferences=body.security_preferences,
        default_views=body.default_views,
        shortcuts=body.shortcuts,
        favorites=body.favorites,
        feature_flags=body.feature_flags,
    )
    return SuccessResponse(message="Settings updated.", data=_to_response(record), meta=_meta())


__all__ = ["router"]
