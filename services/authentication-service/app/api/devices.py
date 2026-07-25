"""GET/DELETE /auth/devices{,/{id}}."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUser, DeviceSvc
from app.schemas.device import DeviceSummary
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/auth/devices", tags=["Devices"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.get("", response_model=SuccessResponse[list[DeviceSummary]])
async def list_devices(
    user: CurrentUser, devices: DeviceSvc
) -> SuccessResponse[list[DeviceSummary]]:
    """List every device on record for the authenticated caller."""
    records = await devices.list_for_user(user.id)
    data = [
        DeviceSummary(
            id=record.id,
            device_name=record.device_name,
            browser=record.browser,
            operating_system=record.operating_system,
            ip_address=record.ip_address,
            location=record.location,
            last_login_at=record.last_login_at,
            is_trusted=record.is_trusted,
            trusted_until=record.trusted_until,
        )
        for record in records
    ]
    return SuccessResponse(message="Devices retrieved.", data=data, meta=_meta())


@router.delete("/{device_id}", response_model=SuccessResponse[dict[str, bool]])
async def revoke_device(
    device_id: UUID, user: CurrentUser, devices: DeviceSvc
) -> SuccessResponse[dict[str, bool]]:
    """Revoke one of the caller's own devices.

    Raises:
        NotFoundError: If no such device belongs to the caller.
    """
    await devices.revoke(user.id, device_id)
    return SuccessResponse(message="Device revoked.", data={"success": True}, meta=_meta())


__all__ = ["router"]
