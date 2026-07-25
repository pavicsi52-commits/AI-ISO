"""``GET /assets/{id}/compliance``. Per docs/038 REST list."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import ComplianceSvc, CurrentUserId
from app.models.asset_compliance import AssetCompliance
from app.schemas.compliance import AssetComplianceResponse
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/assets", tags=["Compliance"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def compliance_to_response(evaluation: AssetCompliance) -> AssetComplianceResponse:
    return AssetComplianceResponse(
        id=evaluation.id,
        managed_asset_id=evaluation.managed_asset_id,
        compliance_type=evaluation.compliance_type,
        status=evaluation.status,
        checked_at=evaluation.checked_at,
        details=evaluation.details,
        exception_reason=evaluation.exception_reason,
    )


@router.get(
    "/{managed_asset_id}/compliance", response_model=SuccessResponse[list[AssetComplianceResponse]]
)
async def list_compliance(
    managed_asset_id: UUID, compliance: ComplianceSvc, _caller: CurrentUserId
) -> SuccessResponse[list[AssetComplianceResponse]]:
    """List every compliance evaluation for a managed asset ("Compliance Reports")."""
    records = await compliance.list_for_managed_asset(managed_asset_id)
    data = [compliance_to_response(record) for record in records]
    return SuccessResponse(message="Compliance evaluations retrieved.", data=data, meta=_meta())


__all__ = ["compliance_to_response", "router"]
