"""Every table this service owns.

Imported as a package by Alembic's ``env.py``, which is what registers
each model with ``Base.metadata`` before autogenerate runs. A model not
re-exported here is a table the migration will not know about.
"""

from __future__ import annotations

from app.models.announcement import NotificationAnnouncement, NotificationBroadcast
from app.models.channel import NotificationChannelConfig
from app.models.delivery import NotificationDelivery, NotificationDeliveryAttempt
from app.models.governance import NotificationAudit, NotificationReport, NotificationStatistic
from app.models.notification import Notification
from app.models.preference import NotificationPreference
from app.models.retry import NotificationDeadLetter, NotificationRetryQueueEntry
from app.models.subscription import NotificationSubscription
from app.models.template import NotificationTemplate, NotificationTemplateVersion

__all__ = [
    "Notification",
    "NotificationAnnouncement",
    "NotificationAudit",
    "NotificationBroadcast",
    "NotificationChannelConfig",
    "NotificationDeadLetter",
    "NotificationDelivery",
    "NotificationDeliveryAttempt",
    "NotificationPreference",
    "NotificationReport",
    "NotificationRetryQueueEntry",
    "NotificationStatistic",
    "NotificationSubscription",
    "NotificationTemplate",
    "NotificationTemplateVersion",
]
