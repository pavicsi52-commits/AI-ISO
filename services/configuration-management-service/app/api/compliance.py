"""``GET /configurations/compliance``. Per docs/039 REST list."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import ComplianceSvc, CurrentUserId
from app.models.configuration_compliance import ConfigurationCompliance
from app.models.enums import ComplianceEvalType
from app.schemas.compliance import ConfigurationComplianceResponse
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/configurations", tags=["Compliance"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def compliance_to_response(
    entry: ConfigurationCompliance,
) -> ConfigurationComplianceResponse:
    return ConfigurationComplianceResponse(
        id=entry.id,
        profile_id=entry.profile_id,
        eval_type=entry.eval_type,
        status=entry.status,
        checked_at=entry.checked_at,
        details=entry.details,
        exception_reason=entry.exception_reason,
    )


@router.get("/compliance", response_model=SuccessResponse[list[ConfigurationComplianceResponse]])
async def list_compliance(
    profile_id: UUID,
    compliance: ComplianceSvc,
    _caller: CurrentUserId,
    eval_type: ComplianceEvalType | None = None,
) -> SuccessResponse[list[ConfigurationComplianceResponse]]:
    """List compliance evaluations recorded for a configuration profile ("Evaluate")."""
    records = await compliance.list_for_profile(profile_id, eval_type=eval_type)
    data = [compliance_to_response(record) for record in records]
    return SuccessResponse(
        message="Configuration compliance evaluations retrieved.", data=data, meta=_meta()
    )


__all__ = ["compliance_to_response", "router"]
