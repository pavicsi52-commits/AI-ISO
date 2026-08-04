"""Every service this service owns -- the only layer touching infrastructure."""

from __future__ import annotations

from app.services.announcement import AnnouncementService
from app.services.broadcast import BroadcastService
from app.services.channel import ChannelConfigService
from app.services.delivery import DeliveryService
from app.services.digest import DigestService
from app.services.notification import NotificationService
from app.services.preference import PreferenceService
from app.services.reporting import AuditService, ReportService, StatisticsService
from app.services.subscription import SubscriptionService
from app.services.template import TemplateService

__all__ = [
    "AnnouncementService",
    "AuditService",
    "BroadcastService",
    "ChannelConfigService",
    "DeliveryService",
    "DigestService",
    "NotificationService",
    "PreferenceService",
    "ReportService",
    "StatisticsService",
    "SubscriptionService",
    "TemplateService",
]
