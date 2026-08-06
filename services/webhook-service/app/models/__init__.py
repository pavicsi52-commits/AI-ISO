"""Every table this service owns -- imported here so Alembic autogenerate
and ``shared_core.database.base.Base.metadata`` see all of them."""

from __future__ import annotations

from app.models.delivery import WebhookDelivery, WebhookDeliveryAttempt
from app.models.endpoint import WebhookEndpoint
from app.models.event import WebhookEvent
from app.models.filter import WebhookFilter
from app.models.governance import WebhookAudit, WebhookReport, WebhookStatistic
from app.models.idempotency import WebhookIdempotencyKey
from app.models.replay import WebhookReplayJob
from app.models.retry import WebhookDeadLetter, WebhookRetryQueueEntry
from app.models.signature import WebhookSignature
from app.models.subscription import WebhookSubscription
from app.models.transformation import WebhookTransformation

__all__ = [
    "WebhookAudit",
    "WebhookDeadLetter",
    "WebhookDelivery",
    "WebhookDeliveryAttempt",
    "WebhookEndpoint",
    "WebhookEvent",
    "WebhookFilter",
    "WebhookIdempotencyKey",
    "WebhookReplayJob",
    "WebhookReport",
    "WebhookRetryQueueEntry",
    "WebhookSignature",
    "WebhookStatistic",
    "WebhookSubscription",
    "WebhookTransformation",
]
