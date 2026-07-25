"""``POST /assets/{id}/assign`` and ``POST /assets/{id}/transfer``. Per docs/038 REST list."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import AssignmentSvc, CurrentUserId, OwnershipSvc
from app.models.asset_assignment import AssetAssignment
from app.models.asset_owner import AssetOwner
from app.schemas.assignment import AssetAssignmentResponse, AssetAssignRequest
from app.schemas.ownership import AssetOwnerResponse, OwnershipTransferRequest
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/assets", tags=["Assignments"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def assignment_to_response(assignment: AssetAssignment) -> AssetAssignmentResponse:
    return AssetAssignmentResponse(
        id=assignment.id,
        managed_asset_id=assignment.managed_asset_id,
        assignee_id=assignment.assignee_id,
        assignment_type=assignment.assignment_type,
        status=assignment.status,
        assigned_by=assignment.assigned_by,
        assigned_at=assignment.assigned_at,
        expires_at=assignment.expires_at,
        returned_at=assignment.returned_at,
        notes=assignment.notes,
    )


def owner_to_response(owner: AssetOwner) -> AssetOwnerResponse:
    return AssetOwnerResponse(
        id=owner.id,
        managed_asset_id=owner.managed_asset_id,
        role=owner.role,
        principal_id=owner.principal_id,
        name=owner.name,
    )


@router.post(
    "/{managed_asset_id}/assign",
    response_model=SuccessResponse[AssetAssignmentResponse],
    status_code=201,
)
async def assign_asset(
    managed_asset_id: UUID,
    body: AssetAssignRequest,
    assignments: AssignmentSvc,
    caller: CurrentUserId,
    organization_id: UUID,
) -> SuccessResponse[AssetAssignmentResponse]:
    """Assign (or reassign) a managed asset to a principal ("Assign Asset"/"Reassign Asset")."""
    assignment = await assignments.assign(
        managed_asset_id,
        organization_id=organization_id,
        assignee_id=body.assignee_id,
        assignment_type=body.assignment_type,
        assigned_by=caller,
        expires_at=body.expires_at,
        notes=body.notes,
    )
    return SuccessResponse(
        message="Asset assigned.", data=assignment_to_response(assignment), meta=_meta()
    )


@router.post(
    "/{managed_asset_id}/transfer",
    response_model=SuccessResponse[AssetOwnerResponse],
    status_code=201,
)
async def transfer_ownership(
    managed_asset_id: UUID,
    body: OwnershipTransferRequest,
    ownership: OwnershipSvc,
    _caller: CurrentUserId,
    organization_id: UUID,
) -> SuccessResponse[AssetOwnerResponse]:
    """Transfer an ownership role on a managed asset ("Transfer Ownership")."""
    owner = await ownership.transfer(
        managed_asset_id,
        organization_id=organization_id,
        role=body.role,
        principal_id=body.principal_id,
        name=body.name,
    )
    return SuccessResponse(
        message="Ownership transferred.", data=owner_to_response(owner), meta=_meta()
    )


__all__ = ["assignment_to_response", "owner_to_response", "router"]
