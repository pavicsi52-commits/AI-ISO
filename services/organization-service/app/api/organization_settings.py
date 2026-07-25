"""``/organizations/{id}/settings``. Per docs/033 REST list."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, SettingsSvc, require_admin, require_member
from app.models.organization_settings import OrganizationSettings
from app.schemas.organization_settings import (
    OrganizationSettingsResponse,
    OrganizationSettingsUpdateRequest,
)
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(
    prefix="/organizations/{organization_id}/settings", tags=["Organization Settings"]
)


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def _to_response(settings: OrganizationSettings) -> OrganizationSettingsResponse:
    return OrganizationSettingsResponse(
        id=settings.id,
        organization_id=settings.organization_id,
        password_policy=settings.password_policy,
        mfa_enforced=settings.mfa_enforced,
        allowed_domains=settings.allowed_domains,
        default_language=settings.default_language,
        default_timezone=settings.default_timezone,
        session_timeout_minutes=settings.session_timeout_minutes,
        data_retention_days=settings.data_retention_days,
        storage_policy=settings.storage_policy,
        notification_policy=settings.notification_policy,
        created_at=settings.created_at,
        updated_at=settings.updated_at,
    )


@router.get(
    "",
    response_model=SuccessResponse[OrganizationSettingsResponse],
    dependencies=[Depends(require_member)],
)
async def get_settings(
    organization_id: UUID, settings: SettingsSvc, _caller: CurrentUserId
) -> SuccessResponse[OrganizationSettingsResponse]:
    """Return an organization's settings, creating defaults if missing."""
    record = await settings.get_or_create(organization_id)
    return SuccessResponse(message="Settings retrieved.", data=_to_response(record), meta=_meta())


@router.put(
    "",
    response_model=SuccessResponse[OrganizationSettingsResponse],
    dependencies=[Depends(require_admin)],
)
async def update_settings(
    organization_id: UUID, body: OrganizationSettingsUpdateRequest, settings: SettingsSvc
) -> SuccessResponse[OrganizationSettingsResponse]:
    """Update an organization's settings ("Settings Changes")."""
    record = await settings.update(
        organization_id,
        password_policy=body.password_policy,
        mfa_enforced=body.mfa_enforced,
        allowed_domains=body.allowed_domains,
        default_language=body.default_language,
        default_timezone=body.default_timezone,
        session_timeout_minutes=body.session_timeout_minutes,
        data_retention_days=body.data_retention_days,
        storage_policy=body.storage_policy,
        notification_policy=body.notification_policy,
    )
    return SuccessResponse(message="Settings updated.", data=_to_response(record), meta=_meta())


__all__ = ["router"]
