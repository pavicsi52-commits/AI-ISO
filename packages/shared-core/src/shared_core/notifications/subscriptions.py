"""Subscriptions.

Per docs/025_Enterprise_Notification_Framework.md.txt "SUBSCRIPTIONS":
Subscribe, Unsubscribe, Topics, Categories, Projects, Organizations,
Broadcast Groups.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from shared_core.notifications.exceptions import SubscriptionError


@dataclass(frozen=True, slots=True)
class Subscription:
    """One user's subscription to a topic ("Topics"/"Categories"/"Projects"/"Organizations")."""

    user_id: str
    topic: str
    subscribed_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class SubscriptionRegistry:
    """An in-memory registry of topic subscriptions, including broadcast groups.

    A "topic" is deliberately generic -- the same mechanism covers a
    category, a project, an organization, or an arbitrary broadcast
    group ("Broadcast Groups"), since all four are just a string key
    every subscriber opts into.
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, set[str]] = {}

    def subscribe(self, user_id: str, topic: str) -> Subscription:
        """Subscribe *user_id* to *topic* ("Subscribe")."""
        self._subscribers.setdefault(topic, set()).add(user_id)
        return Subscription(user_id=user_id, topic=topic)

    def unsubscribe(self, user_id: str, topic: str) -> None:
        """Unsubscribe *user_id* from *topic* ("Unsubscribe").

        Raises:
            SubscriptionError: If *user_id* isn't currently subscribed to *topic*.
        """
        subscribers = self._subscribers.get(topic, set())
        if user_id not in subscribers:
            raise SubscriptionError(f"{user_id!r} is not subscribed to {topic!r}.")
        subscribers.discard(user_id)

    def is_subscribed(self, user_id: str, topic: str) -> bool:
        """Whether *user_id* is currently subscribed to *topic*."""
        return user_id in self._subscribers.get(topic, set())

    def subscribers_of(self, topic: str) -> list[str]:
        """Every user currently subscribed to *topic* ("Broadcast Groups": broadcast recipients)."""
        return sorted(self._subscribers.get(topic, set()))

    def topics_of(self, user_id: str) -> list[str]:
        """Every topic *user_id* is currently subscribed to."""
        return sorted(
            topic for topic, subscribers in self._subscribers.items() if user_id in subscribers
        )


__all__ = ["Subscription", "SubscriptionRegistry"]
