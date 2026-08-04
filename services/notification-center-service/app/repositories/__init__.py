"""Every repository this service owns.

Each is tenant-scoped. The scoped lookups are named ``require_in_org``
rather than overriding the base ``require_by_id``: two same-named methods
of different arity on one class make an unscoped call look correct, which
is how a cross-tenant read gets written.
"""

from __future__ import annotations

from app.repositories.announcement import (
    NotificationAnnouncementRepository,
    NotificationBroadcastRepository,
)
from app.repositories.channel import NotificationChannelConfigRepository
from app.repositories.delivery import (
    NotificationDeliveryAttemptRepository,
    NotificationDeliveryRepository,
)
from app.repositories.governance import (
    NotificationAuditRepository,
    NotificationReportRepository,
    NotificationStatisticRepository,
)
from app.repositories.notification import NotificationRepository
from app.repositories.preference import NotificationPreferenceRepository
from app.repositories.retry import NotificationDeadLetterRepository, NotificationRetryQueueRepository
from app.repositories.subscription import NotificationSubscriptionRepository
from app.repositories.template import (
    NotificationTemplateRepository,
    NotificationTemplateVersionRepository,
)

__all__ = [
    "NotificationAnnouncementRepository",
    "NotificationAuditRepository",
    "NotificationBroadcastRepository",
    "NotificationChannelConfigRepository",
    "NotificationDeadLetterRepository",
    "NotificationDeliveryAttemptRepository",
    "NotificationDeliveryRepository",
    "NotificationPreferenceRepository",
    "NotificationReportRepository",
    "NotificationRepository",
    "NotificationRetryQueueRepository",
    "NotificationStatisticRepository",
    "NotificationSubscriptionRepository",
    "NotificationTemplateRepository",
    "NotificationTemplateVersionRepository",
]
