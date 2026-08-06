"""Subscription management (docs/057 "SUBSCRIPTIONS", "REST APIs")."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, status
from shared_core.logging.context import get_log_context

from app.api.deps import AuditSvc, CurrentUserId, SubscriptionSvc
from app.models.enums import AuditAction
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.webhook import SubscriptionCreateRequest, SubscriptionResponse, SubscriptionUpdateRequest

router = APIRouter(prefix="/webhooks/subscriptions", tags=["Subscriptions"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.get("", response_model=SuccessResponse[list[SubscriptionResponse]], summary="List subscriptions")
async def list_subscriptions(
    organization_id: UUID, subscriptions: SubscriptionSvc
) -> SuccessResponse[list[SubscriptionResponse]]:
    """Subscriptions in this organization."""
    rows = await subscriptions.list_subscriptions(organization_id)
    return SuccessResponse(
        message="Subscriptions listed.",
        data=[SubscriptionResponse.model_validate(r) for r in rows],
        meta=_meta(),
    )


@router.get(
    "/{subscription_id}",
    response_model=SuccessResponse[SubscriptionResponse],
    summary="Get a subscription",
)
async def get_subscription(
    organization_id: UUID, subscription_id: UUID, subscriptions: SubscriptionSvc
) -> SuccessResponse[SubscriptionResponse]:
    """One subscription."""
    found = await subscriptions.get(organization_id, subscription_id)
    return SuccessResponse(
        message="Subscription found.", data=SubscriptionResponse.model_validate(found), meta=_meta()
    )


@router.post(
    "",
    response_model=SuccessResponse[SubscriptionResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create a subscription",
)
async def create_subscription(
    organization_id: UUID,
    body: SubscriptionCreateRequest,
    subscriptions: SubscriptionSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[SubscriptionResponse]:
    """Register a new subscription."""
    created = await subscriptions.create(
        organization_id,
        endpoint_id=body.endpoint_id,
        scope=body.scope,
        scope_reference=body.scope_reference,
        event_types=body.event_types,
        condition_expression=body.condition_expression,
    )
    await audit.record(
        organization_id,
        action=AuditAction.SUBSCRIPTION_CREATED,
        entity_type="subscription",
        entity_id=created.id,
        actor_id=str(caller),
        summary=f"Created subscription {created.id}.",
    )
    return SuccessResponse(
        message="Subscription created.", data=SubscriptionResponse.model_validate(created), meta=_meta()
    )


@router.put(
    "/{subscription_id}",
    response_model=SuccessResponse[SubscriptionResponse],
    summary="Update a subscription",
)
async def update_subscription(
    organization_id: UUID,
    subscription_id: UUID,
    body: SubscriptionUpdateRequest,
    subscriptions: SubscriptionSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[SubscriptionResponse]:
    """Edit a subscription's editable fields."""
    fields = body.model_dump(exclude_unset=True)
    updated = await subscriptions.update(organization_id, subscription_id, **fields)
    await audit.record(
        organization_id,
        action=AuditAction.SUBSCRIPTION_UPDATED,
        entity_type="subscription",
        entity_id=updated.id,
        actor_id=str(caller),
        summary=f"Updated subscription {updated.id}.",
    )
    return SuccessResponse(
        message="Subscription updated.", data=SubscriptionResponse.model_validate(updated), meta=_meta()
    )


@router.delete(
    "/{subscription_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a subscription"
)
async def delete_subscription(
    organization_id: UUID,
    subscription_id: UUID,
    subscriptions: SubscriptionSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> None:
    """Remove a subscription."""
    await subscriptions.delete(organization_id, subscription_id)
    await audit.record(
        organization_id,
        action=AuditAction.SUBSCRIPTION_DELETED,
        entity_type="subscription",
        entity_id=subscription_id,
        actor_id=str(caller),
        summary=f"Deleted subscription {subscription_id}.",
    )


__all__ = ["router"]
