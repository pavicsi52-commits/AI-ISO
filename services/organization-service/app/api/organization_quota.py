"""``/organizations/{id}/quotas``. Per docs/033 REST list."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, QuotaSvc, require_admin, require_member
from app.models.organization_quota import OrganizationQuota
from app.schemas.organization_quota import OrganizationQuotaResponse, OrganizationQuotaUpdateRequest
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/organizations/{organization_id}/quotas", tags=["Organization Quotas"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def _to_response(quota: OrganizationQuota) -> OrganizationQuotaResponse:
    return OrganizationQuotaResponse(
        id=quota.id,
        organization_id=quota.organization_id,
        max_users=quota.max_users,
        max_projects=quota.max_projects,
        max_assets=quota.max_assets,
        max_storage_gb=quota.max_storage_gb,
        max_workflows=quota.max_workflows,
        max_automation_jobs=quota.max_automation_jobs,
        max_connectors=quota.max_connectors,
        max_api_calls_per_day=quota.max_api_calls_per_day,
        max_ai_requests_per_day=quota.max_ai_requests_per_day,
        max_plugins=quota.max_plugins,
        created_at=quota.created_at,
        updated_at=quota.updated_at,
    )


@router.get(
    "",
    response_model=SuccessResponse[OrganizationQuotaResponse],
    dependencies=[Depends(require_member)],
)
async def get_quotas(
    organization_id: UUID, quotas: QuotaSvc, _caller: CurrentUserId
) -> SuccessResponse[OrganizationQuotaResponse]:
    """Return an organization's quotas, creating defaults if missing."""
    record = await quotas.get_or_create(organization_id)
    return SuccessResponse(message="Quotas retrieved.", data=_to_response(record), meta=_meta())


@router.put(
    "",
    response_model=SuccessResponse[OrganizationQuotaResponse],
    dependencies=[Depends(require_admin)],
)
async def update_quotas(
    organization_id: UUID, body: OrganizationQuotaUpdateRequest, quotas: QuotaSvc
) -> SuccessResponse[OrganizationQuotaResponse]:
    """Update an organization's quotas ("Quota Changes")."""
    record = await quotas.update(
        organization_id,
        max_users=body.max_users,
        max_projects=body.max_projects,
        max_assets=body.max_assets,
        max_storage_gb=body.max_storage_gb,
        max_workflows=body.max_workflows,
        max_automation_jobs=body.max_automation_jobs,
        max_connectors=body.max_connectors,
        max_api_calls_per_day=body.max_api_calls_per_day,
        max_ai_requests_per_day=body.max_ai_requests_per_day,
        max_plugins=body.max_plugins,
    )
    return SuccessResponse(message="Quotas updated.", data=_to_response(record), meta=_meta())


__all__ = ["router"]
