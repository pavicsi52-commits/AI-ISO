"""Enterprise Notification Framework factory.

Assembles the channel registry, router, and dispatcher into one
:class:`~shared_core.notifications.manager.NotificationManager` a
service builds exactly once at startup -- mirroring
:func:`shared_core.queue.factory.create_queue_framework` (Prompt 021).

Only builds the :class:`~shared_core.notifications.email.EmailChannel`
automatically (it's the one channel with dedicated
:class:`~shared_core.config.settings.EmailSettings`, per
docs/013_Enterprise_Configuration_Framework.md.txt); every other
channel (SMS, Push, Slack, Teams, Discord, Webhook, In-App) needs
per-provider configuration (a webhook URL, an API endpoint, ...) this
framework has no default for, so a caller registers those explicitly
via the returned manager's ``channels`` registry.
"""

from __future__ import annotations

from shared_core.config.settings import EmailSettings
from shared_core.notifications.channels import ChannelRegistry, NotificationMessage
from shared_core.notifications.dispatcher import NotificationDispatcher
from shared_core.notifications.email import EmailChannel
from shared_core.notifications.history import HistoryStore
from shared_core.notifications.manager import NotificationManager
from shared_core.notifications.preferences import PreferencesStore
from shared_core.notifications.retry import DeadLetterStore, notification_retry_policy
from shared_core.notifications.router import NotificationRouter


def _user_id_as_email_address(message: NotificationMessage) -> str:
    """The default email address resolver: the message's own ``user_id``.

    A real service almost always wants to resolve a user ID to an
    actual email address via its own user directory -- pass a different
    ``to_address_resolver`` to :class:`~shared_core.notifications.email
    .EmailChannel` directly (via the returned manager's ``channels``
    registry) to override this.
    """
    return message.user_id or ""


def create_notification_framework(
    *, email_settings: EmailSettings | None = None
) -> NotificationManager:
    """Build a :class:`NotificationManager` from Configuration Framework settings."""
    channels = ChannelRegistry()
    if email_settings is not None and email_settings.email_enabled:
        channels.register(
            EmailChannel(email_settings, to_address_resolver=_user_id_as_email_address)
        )

    preferences = PreferencesStore()
    history = HistoryStore()
    dead_letters = DeadLetterStore()
    return NotificationManager(
        channels=channels,
        dispatcher=NotificationDispatcher(
            channels=channels,
            history=history,
            dead_letters=dead_letters,
            retry_policy=notification_retry_policy(),
        ),
        router=NotificationRouter(preferences),
        preferences=preferences,
        history=history,
        dead_letters=dead_letters,
    )


__all__ = ["create_notification_framework"]
