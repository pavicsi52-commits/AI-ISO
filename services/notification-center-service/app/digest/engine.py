"""Digest grouping -- a thin adapter onto `shared_core.notifications.digest`.

Grouping-by-category and duplicate removal delegate entirely to
`shared_core.notifications.digest.build_digest`. Formatting a built
:class:`~shared_core.notifications.digest.Digest` into an actual
notification body is this module's one genuine addition:
`shared_core.notifications.digest`'s own docstring defers that step to
"the renderer", but `shared_core.notifications.renderer` only renders a
*template* against variables -- there is no digest-shaped template built
into the framework for it to render.
"""

from __future__ import annotations

from shared_core.enums.notification_channel import NotificationChannel
from shared_core.notifications.channels import NotificationMessage
from shared_core.notifications.delivery import DeliveryStatus
from shared_core.notifications.digest import Digest, build_digest

from app.models.enums import (
    NotificationCategory,
    NotificationPriority,
    to_shared_notification_type,
    to_shared_priority,
)


def to_shared_message(
    *,
    notification_id: str,
    category: NotificationCategory,
    priority: NotificationPriority,
    subject: str | None,
    body: str,
    user_id: str,
) -> NotificationMessage:
    """Build the `shared_core` message shape :func:`build_user_digest` groups and deduplicates.

    This service's own persisted :class:`~app.models.notification
    .Notification` row remains the source of truth; this is only the
    shape `shared_core`'s dedupe key (type, subject, body) reads.
    """
    return NotificationMessage(
        notification_id=notification_id,
        channel=NotificationChannel.IN_APP,
        notification_type=to_shared_notification_type(category),
        priority=to_shared_priority(priority),
        body=body,
        subject=subject,
        user_id=user_id,
        status=DeliveryStatus.PENDING,
    )


def build_user_digest(
    user_id: str, messages: list[NotificationMessage], *, max_items: int
) -> Digest:
    """Group and deduplicate *messages* for one digest."""
    return build_digest(user_id, messages, max_items=max_items)


def render_digest_body(digest: Digest) -> str:
    """Format a built :class:`~shared_core.notifications.digest.Digest` into one notification body."""  # noqa: E501
    if not digest.groups:
        return "No new notifications."
    lines = [f"You have {digest.total_count} new notification(s):", ""]
    for group in digest.groups:
        lines.append(f"## {group.notification_type.replace('_', ' ').title()}")
        for message in group.messages:
            headline = message.subject or message.body
            lines.append(f"- {headline}")
        lines.append("")
    return "\n".join(lines).rstrip()


__all__ = ["build_user_digest", "render_digest_body", "to_shared_message"]
