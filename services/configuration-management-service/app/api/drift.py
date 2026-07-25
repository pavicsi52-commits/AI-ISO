"""``GET /configurations/drift``. Per docs/039 REST list."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, DriftSvc
from app.models.configuration_drift import ConfigurationDrift
from app.schemas.drift import ConfigurationDriftResponse
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/configurations", tags=["Drift"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def drift_to_response(drift: ConfigurationDrift) -> ConfigurationDriftResponse:
    return ConfigurationDriftResponse(
        id=drift.id,
        profile_id=drift.profile_id,
        managed_asset_id=drift.managed_asset_id,
        drift_type=drift.drift_type,
        status=drift.status,
        detected_at=drift.detected_at,
        details=drift.details,
        resolved_at=drift.resolved_at,
        resolved_by=drift.resolved_by,
    )


@router.get("/drift", response_model=SuccessResponse[list[ConfigurationDriftResponse]])
async def list_drift(
    organization_id: UUID,
    drift: DriftSvc,
    _caller: CurrentUserId,
    profile_id: UUID | None = None,
) -> SuccessResponse[list[ConfigurationDriftResponse]]:
    """List detected configuration drift ("Detect"), narrowed to
    *profile_id* if given, otherwise every unresolved drift instance in
    *organization_id*.
    """
    records = (
        await drift.list_for_profile(profile_id)
        if profile_id is not None
        else await drift.list_unresolved_for_org(organization_id)
    )
    data = [drift_to_response(record) for record in records]
    return SuccessResponse(message="Configuration drift retrieved.", data=data, meta=_meta())


__all__ = ["drift_to_response", "router"]
