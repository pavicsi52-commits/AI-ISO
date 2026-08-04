"""Subscription management (docs/055 "SUBSCRIPTIONS")."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, status
from shared_core.logging.context import get_log_context

from app.api.deps import AuditSvc, CurrentUserId, SubscriptionSvc
from app.models.enums import AuditAction, subscription_kind_of
from app.schemas.notification import SubscriptionCreateRequest, SubscriptionResponse
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/notifications/subscriptions", tags=["Subscriptions"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.get(
    "", response_model=SuccessResponse[list[SubscriptionResponse]], summary="List the caller's own subscriptions"
)
async def list_subscriptions(
    organization_id: UUID, subscriptions: SubscriptionSvc, caller: CurrentUserId
) -> SuccessResponse[list[SubscriptionResponse]]:
    """Every subscription the calling user currently holds."""
    rows = await subscriptions.list_for_user(organization_id, str(caller))
    return SuccessResponse(
        message="Subscriptions listed.",
        data=[SubscriptionResponse.model_validate(row) for row in rows],
        meta=_meta(),
    )


@router.post(
    "",
    response_model=SuccessResponse[SubscriptionResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Subscribe to a topic",
)
async def create_subscription(
    organization_id: UUID,
    body: SubscriptionCreateRequest,
    subscriptions: SubscriptionSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[SubscriptionResponse]:
    """Subscribe a user to a topic ("Subscribe")."""
    created = await subscriptions.subscribe(
        organization_id,
        body.user_id,
        body.subscription_kind,
        body.target,
        webhook_url=body.webhook_url,
    )
    await audit.record(
        organization_id,
        action=AuditAction.SUBSCRIPTION_CREATED,
        entity_type="subscription",
        entity_id=created.id,
        actor_id=str(caller),
        summary=f"{body.user_id!r} subscribed to {body.target!r}.",
    )
    return SuccessResponse(
        message="Subscribed.", data=SubscriptionResponse.model_validate(created), meta=_meta()
    )


@router.delete("", status_code=status.HTTP_204_NO_CONTENT, summary="Unsubscribe from a topic")
async def delete_subscription(
    organization_id: UUID,
    user_id: str,
    subscription_kind: str,
    target: str,
    subscriptions: SubscriptionSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> None:
    """Unsubscribe a user from a topic ("Unsubscribe")."""
    await subscriptions.unsubscribe(organization_id, user_id, subscription_kind_of(subscription_kind), target)
    await audit.record(
        organization_id,
        action=AuditAction.SUBSCRIPTION_REMOVED,
        entity_type="subscription",
        actor_id=str(caller),
        summary=f"{user_id!r} unsubscribed from {target!r}.",
    )


__all__ = ["router"]
