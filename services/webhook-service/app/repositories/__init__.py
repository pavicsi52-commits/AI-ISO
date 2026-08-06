"""Every repository this service owns.

Each is tenant-scoped. The scoped lookups are named ``require_in_org``
rather than overriding the base ``require_by_id`` -- two same-named
methods of different arity on one class make an unscoped call look
correct, which is how a cross-tenant read gets written.
"""

from __future__ import annotations

from app.repositories.delivery import WebhookDeliveryAttemptRepository, WebhookDeliveryRepository
from app.repositories.endpoint import WebhookEndpointRepository
from app.repositories.event import WebhookEventRepository
from app.repositories.filter import WebhookFilterRepository
from app.repositories.governance import (
    WebhookAuditRepository,
    WebhookReportRepository,
    WebhookStatisticRepository,
)
from app.repositories.idempotency import WebhookIdempotencyKeyRepository
from app.repositories.replay import WebhookReplayJobRepository
from app.repositories.retry import WebhookDeadLetterRepository, WebhookRetryQueueRepository
from app.repositories.signature import WebhookSignatureRepository
from app.repositories.subscription import WebhookSubscriptionRepository
from app.repositories.transformation import WebhookTransformationRepository

__all__ = [
    "WebhookAuditRepository",
    "WebhookDeadLetterRepository",
    "WebhookDeliveryAttemptRepository",
    "WebhookDeliveryRepository",
    "WebhookEndpointRepository",
    "WebhookEventRepository",
    "WebhookFilterRepository",
    "WebhookIdempotencyKeyRepository",
    "WebhookReplayJobRepository",
    "WebhookReportRepository",
    "WebhookRetryQueueRepository",
    "WebhookSignatureRepository",
    "WebhookStatisticRepository",
    "WebhookSubscriptionRepository",
    "WebhookTransformationRepository",
]
