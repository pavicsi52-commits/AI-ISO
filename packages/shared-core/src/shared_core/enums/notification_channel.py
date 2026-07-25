"""Notification channel enumeration."""

from enum import StrEnum


class NotificationChannel(StrEnum):
    """How a notification is delivered.

    Per docs/025_Enterprise_Notification_Framework.md.txt "CHANNELS".
    "Every channel shall implement the same interface" --
    :mod:`shared_core.notifications.channels`'s ``Channel`` protocol.
    """

    EMAIL = "email"
    SMS = "sms"
    PUSH = "push"
    IN_APP = "in_app"
    SLACK = "slack"
    TEAMS = "teams"
    DISCORD = "discord"
    WEBHOOK = "webhook"
