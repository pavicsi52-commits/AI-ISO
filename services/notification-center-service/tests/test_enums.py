"""Pure tests for app/models/enums.py -- no database, no fixtures."""

from __future__ import annotations

import pytest
from shared_core.enums.notification_channel import NotificationChannel as SharedNotificationChannel
from shared_core.enums.notification_type import NotificationType as SharedNotificationType
from shared_core.enums.priority import Priority as SharedPriority
from shared_core.notifications.digest import DigestFrequency as SharedDigestFrequency
from shared_core.notifications.templates import TemplateFormat as SharedTemplateFormat

from app.models.enums import (
    OPEN_NOTIFICATION_STATUSES,
    TERMINAL_NOTIFICATION_STATUSES,
    AnnouncementScope,
    AnnouncementStatus,
    BroadcastStatus,
    DigestFrequency,
    NotificationCategory,
    NotificationChannelKind,
    NotificationPriority,
    NotificationStatus,
    ReportFormat,
    ReportKind,
    ReportStatus,
    SubscriptionKind,
    TemplateFormat,
    announcement_scope_of,
    announcement_status_of,
    broadcast_status_of,
    digest_frequency_of,
    notification_category_of,
    notification_channel_kind_of,
    notification_priority_of,
    notification_status_of,
    priority_at_least,
    report_format_of,
    report_kind_of,
    report_status_of,
    subscription_kind_of,
    template_format_of,
    to_shared_channel,
    to_shared_digest_frequency,
    to_shared_notification_type,
    to_shared_priority,
    to_shared_template_format,
)

pytestmark = pytest.mark.asyncio


class TestToSharedChannel:
    async def test_mobile_push_maps_to_shared_push(self) -> None:
        assert to_shared_channel(NotificationChannelKind.MOBILE_PUSH) == SharedNotificationChannel.PUSH

    async def test_browser_push_maps_to_shared_push(self) -> None:
        assert (
            to_shared_channel(NotificationChannelKind.BROWSER_PUSH) == SharedNotificationChannel.PUSH
        )

    async def test_rest_callback_maps_to_shared_webhook(self) -> None:
        assert (
            to_shared_channel(NotificationChannelKind.REST_CALLBACK)
            == SharedNotificationChannel.WEBHOOK
        )

    async def test_custom_maps_to_shared_webhook(self) -> None:
        assert to_shared_channel(NotificationChannelKind.CUSTOM) == SharedNotificationChannel.WEBHOOK

    @pytest.mark.parametrize(
        ("channel", "expected"),
        [
            (NotificationChannelKind.EMAIL, SharedNotificationChannel.EMAIL),
            (NotificationChannelKind.SMS, SharedNotificationChannel.SMS),
            (NotificationChannelKind.SLACK, SharedNotificationChannel.SLACK),
            (NotificationChannelKind.TEAMS, SharedNotificationChannel.TEAMS),
            (NotificationChannelKind.DISCORD, SharedNotificationChannel.DISCORD),
            (NotificationChannelKind.WEBHOOK, SharedNotificationChannel.WEBHOOK),
            (NotificationChannelKind.IN_APP, SharedNotificationChannel.IN_APP),
        ],
    )
    async def test_every_other_member_is_a_direct_one_to_one_match(
        self, channel: NotificationChannelKind, expected: SharedNotificationChannel
    ) -> None:
        assert to_shared_channel(channel) == expected


class TestToSharedNotificationType:
    @pytest.mark.parametrize(
        ("category", "expected"),
        [
            (NotificationCategory.ALERT, SharedNotificationType.WARNING),
            (NotificationCategory.FAILURE, SharedNotificationType.ERROR),
            (NotificationCategory.APPROVAL_REQUEST, SharedNotificationType.APPROVAL),
            (NotificationCategory.ASSIGNMENT, SharedNotificationType.WORKFLOW),
            (NotificationCategory.SYSTEM_ANNOUNCEMENT, SharedNotificationType.SYSTEM),
            (NotificationCategory.MAINTENANCE_NOTICE, SharedNotificationType.MAINTENANCE),
            (NotificationCategory.DIGEST, SharedNotificationType.INFORMATION),
            (NotificationCategory.CUSTOM, SharedNotificationType.INFORMATION),
        ],
    )
    async def test_remapped_categories(
        self, category: NotificationCategory, expected: SharedNotificationType
    ) -> None:
        assert to_shared_notification_type(category) == expected

    @pytest.mark.parametrize(
        ("category", "expected"),
        [
            (NotificationCategory.WARNING, SharedNotificationType.WARNING),
            (NotificationCategory.INFORMATION, SharedNotificationType.INFORMATION),
            (NotificationCategory.SUCCESS, SharedNotificationType.SUCCESS),
            (NotificationCategory.CRITICAL, SharedNotificationType.CRITICAL),
            (NotificationCategory.REMINDER, SharedNotificationType.REMINDER),
        ],
    )
    async def test_every_other_member_is_a_direct_one_to_one_match(
        self, category: NotificationCategory, expected: SharedNotificationType
    ) -> None:
        assert to_shared_notification_type(category) == expected


class TestToSharedPriority:
    @pytest.mark.parametrize(
        ("priority", "expected"),
        [
            (NotificationPriority.CRITICAL, SharedPriority.CRITICAL),
            (NotificationPriority.HIGH, SharedPriority.HIGH),
            (NotificationPriority.NORMAL, SharedPriority.NORMAL),
            (NotificationPriority.LOW, SharedPriority.LOW),
            (NotificationPriority.BACKGROUND, SharedPriority.BACKGROUND),
        ],
    )
    async def test_direct_one_to_one_mapping(
        self, priority: NotificationPriority, expected: SharedPriority
    ) -> None:
        assert to_shared_priority(priority) == expected


class TestToSharedTemplateFormat:
    @pytest.mark.parametrize(
        ("template_format", "expected"),
        [
            (TemplateFormat.HTML, SharedTemplateFormat.HTML),
            (TemplateFormat.MARKDOWN, SharedTemplateFormat.MARKDOWN),
            (TemplateFormat.PLAIN_TEXT, SharedTemplateFormat.PLAIN_TEXT),
        ],
    )
    async def test_direct_one_to_one_mapping(
        self, template_format: TemplateFormat, expected: SharedTemplateFormat
    ) -> None:
        assert to_shared_template_format(template_format) == expected


class TestToSharedDigestFrequency:
    @pytest.mark.parametrize(
        ("frequency", "expected"),
        [
            (DigestFrequency.NONE, SharedDigestFrequency.NONE),
            (DigestFrequency.HOURLY, SharedDigestFrequency.HOURLY),
            (DigestFrequency.DAILY, SharedDigestFrequency.DAILY),
            (DigestFrequency.WEEKLY, SharedDigestFrequency.WEEKLY),
            (DigestFrequency.MONTHLY, SharedDigestFrequency.MONTHLY),
        ],
    )
    async def test_direct_one_to_one_mapping(
        self, frequency: DigestFrequency, expected: SharedDigestFrequency
    ) -> None:
        assert to_shared_digest_frequency(frequency) == expected


class TestNormalizers:
    async def test_notification_channel_kind_of_accepts_enum_member(self) -> None:
        assert (
            notification_channel_kind_of(NotificationChannelKind.EMAIL)
            == NotificationChannelKind.EMAIL
        )

    async def test_notification_channel_kind_of_accepts_raw_string(self) -> None:
        assert notification_channel_kind_of("email") == NotificationChannelKind.EMAIL

    async def test_notification_category_of_accepts_enum_member(self) -> None:
        assert notification_category_of(NotificationCategory.ALERT) == NotificationCategory.ALERT

    async def test_notification_category_of_accepts_raw_string(self) -> None:
        assert notification_category_of("alert") == NotificationCategory.ALERT

    async def test_notification_status_of_accepts_enum_member(self) -> None:
        assert notification_status_of(NotificationStatus.FAILED) == NotificationStatus.FAILED

    async def test_notification_status_of_accepts_raw_string(self) -> None:
        assert notification_status_of("failed") == NotificationStatus.FAILED

    async def test_notification_priority_of_accepts_enum_member(self) -> None:
        assert (
            notification_priority_of(NotificationPriority.CRITICAL) == NotificationPriority.CRITICAL
        )

    async def test_notification_priority_of_accepts_raw_string(self) -> None:
        assert notification_priority_of("critical") == NotificationPriority.CRITICAL

    async def test_template_format_of_accepts_enum_member(self) -> None:
        assert template_format_of(TemplateFormat.HTML) == TemplateFormat.HTML

    async def test_template_format_of_accepts_raw_string(self) -> None:
        assert template_format_of("html") == TemplateFormat.HTML

    async def test_digest_frequency_of_accepts_enum_member(self) -> None:
        assert digest_frequency_of(DigestFrequency.DAILY) == DigestFrequency.DAILY

    async def test_digest_frequency_of_accepts_raw_string(self) -> None:
        assert digest_frequency_of("daily") == DigestFrequency.DAILY

    async def test_subscription_kind_of_accepts_enum_member(self) -> None:
        assert subscription_kind_of(SubscriptionKind.EVENT) == SubscriptionKind.EVENT

    async def test_subscription_kind_of_accepts_raw_string(self) -> None:
        assert subscription_kind_of("event") == SubscriptionKind.EVENT

    async def test_announcement_scope_of_accepts_enum_member(self) -> None:
        assert announcement_scope_of(AnnouncementScope.SYSTEM) == AnnouncementScope.SYSTEM

    async def test_announcement_scope_of_accepts_raw_string(self) -> None:
        assert announcement_scope_of("system") == AnnouncementScope.SYSTEM

    async def test_announcement_status_of_accepts_enum_member(self) -> None:
        assert announcement_status_of(AnnouncementStatus.DRAFT) == AnnouncementStatus.DRAFT

    async def test_announcement_status_of_accepts_raw_string(self) -> None:
        assert announcement_status_of("draft") == AnnouncementStatus.DRAFT

    async def test_broadcast_status_of_accepts_enum_member(self) -> None:
        assert broadcast_status_of(BroadcastStatus.PENDING) == BroadcastStatus.PENDING

    async def test_broadcast_status_of_accepts_raw_string(self) -> None:
        assert broadcast_status_of("pending") == BroadcastStatus.PENDING

    async def test_report_kind_of_accepts_enum_member(self) -> None:
        assert report_kind_of(ReportKind.DELIVERY) == ReportKind.DELIVERY

    async def test_report_kind_of_accepts_raw_string(self) -> None:
        assert report_kind_of("delivery") == ReportKind.DELIVERY

    async def test_report_format_of_accepts_enum_member(self) -> None:
        assert report_format_of(ReportFormat.JSON) == ReportFormat.JSON

    async def test_report_format_of_accepts_raw_string(self) -> None:
        assert report_format_of("json") == ReportFormat.JSON

    async def test_report_status_of_accepts_enum_member(self) -> None:
        assert report_status_of(ReportStatus.PENDING) == ReportStatus.PENDING

    async def test_report_status_of_accepts_raw_string(self) -> None:
        assert report_status_of("pending") == ReportStatus.PENDING


class TestPriorityAtLeast:
    async def test_critical_is_at_least_as_urgent_as_normal(self) -> None:
        assert (
            priority_at_least(NotificationPriority.CRITICAL, floor=NotificationPriority.NORMAL)
            is True
        )

    async def test_low_is_not_at_least_as_urgent_as_normal(self) -> None:
        assert (
            priority_at_least(NotificationPriority.LOW, floor=NotificationPriority.NORMAL) is False
        )

    async def test_a_priority_is_at_least_as_urgent_as_itself(self) -> None:
        assert (
            priority_at_least(NotificationPriority.NORMAL, floor=NotificationPriority.NORMAL) is True
        )

    async def test_background_is_not_at_least_as_urgent_as_critical(self) -> None:
        assert (
            priority_at_least(NotificationPriority.BACKGROUND, floor=NotificationPriority.CRITICAL)
            is False
        )

    async def test_high_is_not_at_least_as_urgent_as_critical(self) -> None:
        assert (
            priority_at_least(NotificationPriority.HIGH, floor=NotificationPriority.CRITICAL)
            is False
        )


class TestDerivedStatusSets:
    async def test_open_and_terminal_statuses_are_disjoint(self) -> None:
        assert OPEN_NOTIFICATION_STATUSES.isdisjoint(TERMINAL_NOTIFICATION_STATUSES)

    @pytest.mark.parametrize(
        "status",
        [
            NotificationStatus.CREATED,
            NotificationStatus.QUEUED,
            NotificationStatus.SENDING,
            NotificationStatus.SENT,
        ],
    )
    async def test_open_statuses_are_in_open_and_not_in_terminal(
        self, status: NotificationStatus
    ) -> None:
        assert status in OPEN_NOTIFICATION_STATUSES
        assert status not in TERMINAL_NOTIFICATION_STATUSES

    @pytest.mark.parametrize(
        "status",
        [
            NotificationStatus.DELIVERED,
            NotificationStatus.READ,
            NotificationStatus.ACKNOWLEDGED,
            NotificationStatus.FAILED,
            NotificationStatus.EXPIRED,
            NotificationStatus.CANCELLED,
        ],
    )
    async def test_terminal_statuses_are_in_terminal_and_not_in_open(
        self, status: NotificationStatus
    ) -> None:
        assert status in TERMINAL_NOTIFICATION_STATUSES
        assert status not in OPEN_NOTIFICATION_STATUSES
