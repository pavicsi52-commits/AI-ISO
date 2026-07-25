"""``/policies``. Per docs/032 REST list."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, PolicySvc
from app.authorization.guard import require_permission
from app.models.enums import PermissionAction, ResourceType
from app.schemas.policy import (
    PolicyConditionResponse,
    PolicyCreateRequest,
    PolicyResponse,
    PolicyUpdateRequest,
)
from app.schemas.response import ResponseMeta, SuccessResponse
from app.services.policy import ConditionInput, PolicyWithConditions

router = APIRouter(prefix="/policies", tags=["Policies"])

_ManagePolicies = Depends(require_permission(ResourceType.SETTINGS, PermissionAction.MANAGE))


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def _to_response(entry: PolicyWithConditions) -> PolicyResponse:
    policy = entry.policy
    return PolicyResponse(
        id=policy.id,
        name=policy.name,
        code=policy.code,
        description=policy.description,
        effect=policy.effect,
        resource_type=policy.resource_type,
        action=policy.action,
        priority=policy.priority,
        status=policy.status,
        conditions=[
            PolicyConditionResponse(
                id=c.id,
                condition_type=c.condition_type,
                field=c.field,
                operator=c.operator,
                value=c.value,
            )
            for c in entry.conditions
        ],
        metadata=policy.metadata_,
        created_at=policy.created_at,
        updated_at=policy.updated_at,
    )


@router.get("", response_model=SuccessResponse[list[PolicyResponse]])
async def list_policies(
    policies: PolicySvc, _caller: CurrentUserId
) -> SuccessResponse[list[PolicyResponse]]:
    """List every active policy ("Policy Engine")."""
    records = await policies.list_active()
    return SuccessResponse(
        message="Policies retrieved.", data=[_to_response(p) for p in records], meta=_meta()
    )


@router.post(
    "",
    response_model=SuccessResponse[PolicyResponse],
    status_code=201,
    dependencies=[_ManagePolicies],
)
async def create_policy(
    body: PolicyCreateRequest, policies: PolicySvc
) -> SuccessResponse[PolicyResponse]:
    """Create a new policy, its conditions, and its initial assignment."""
    entry = await policies.create(
        name=body.name,
        code=body.code,
        description=body.description,
        effect=body.effect,
        resource_type=body.resource_type,
        action=body.action,
        priority=body.priority,
        conditions=[
            ConditionInput(
                condition_type=c.condition_type, field=c.field, operator=c.operator, value=c.value
            )
            for c in body.conditions
        ],
        subject_type=body.subject_type,
        subject_id=body.subject_id,
        metadata=body.metadata,
    )
    return SuccessResponse(message="Policy created.", data=_to_response(entry), meta=_meta())


@router.put(
    "/{policy_id}", response_model=SuccessResponse[PolicyResponse], dependencies=[_ManagePolicies]
)
async def update_policy(
    policy_id: UUID, body: PolicyUpdateRequest, policies: PolicySvc
) -> SuccessResponse[PolicyResponse]:
    """Update a policy's fields and replace its condition set."""
    entry = await policies.update(
        policy_id,
        name=body.name,
        description=body.description,
        effect=body.effect,
        resource_type=body.resource_type,
        action=body.action,
        priority=body.priority,
        status=body.status,
        conditions=[
            ConditionInput(
                condition_type=c.condition_type, field=c.field, operator=c.operator, value=c.value
            )
            for c in body.conditions
        ],
        metadata=body.metadata,
    )
    return SuccessResponse(message="Policy updated.", data=_to_response(entry), meta=_meta())


@router.delete(
    "/{policy_id}",
    response_model=SuccessResponse[dict[str, bool]],
    dependencies=[_ManagePolicies],
)
async def delete_policy(policy_id: UUID, policies: PolicySvc) -> SuccessResponse[dict[str, bool]]:
    """Delete a policy."""
    await policies.delete(policy_id)
    return SuccessResponse(message="Policy deleted.", data={"success": True}, meta=_meta())


__all__ = ["router"]
