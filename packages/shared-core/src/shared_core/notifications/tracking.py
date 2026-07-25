"""Open/click tracking.

Per docs/025_Enterprise_Notification_Framework.md.txt "ANALYTICS":
Opened, Clicked. This module builds the tracking URLs a rendered
notification embeds (a 1x1 pixel for opens, a redirect wrapper for
clicks) and records the callbacks a service's own web-facing endpoint
receives when a recipient triggers one -- serving that endpoint itself
is business/HTTP-API surface out of this framework's scope
("DO NOT IMPLEMENT": REST APIs).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from urllib.parse import quote, urlencode


@dataclass(frozen=True, slots=True)
class TrackingEvent:
    """One recorded open or click."""

    notification_id: str
    kind: str
    recorded_at: float
    target_url: str | None = None


class TrackingRecorder:
    """An in-memory record of open/click callbacks, for analytics to read."""

    def __init__(self) -> None:
        self._events: list[TrackingEvent] = []

    def record_open(self, notification_id: str) -> None:
        """Record that *notification_id* was opened."""
        self._events.append(
            TrackingEvent(notification_id=notification_id, kind="open", recorded_at=time.time())
        )

    def record_click(self, notification_id: str, *, target_url: str) -> None:
        """Record that a link in *notification_id* was clicked."""
        self._events.append(
            TrackingEvent(
                notification_id=notification_id,
                kind="click",
                recorded_at=time.time(),
                target_url=target_url,
            )
        )

    def events_for(self, notification_id: str) -> list[TrackingEvent]:
        """Every retained tracking event for *notification_id*."""
        return [event for event in self._events if event.notification_id == notification_id]

    def all_events(self) -> list[TrackingEvent]:
        """Every retained tracking event."""
        return list(self._events)


def build_open_tracking_url(notification_id: str, *, base_url: str) -> str:
    """Build a 1x1-pixel tracking URL a rendered notification's body embeds."""
    return f"{base_url.rstrip('/')}/track/open/{quote(notification_id)}"


def build_click_tracking_url(notification_id: str, target_url: str, *, base_url: str) -> str:
    """Build a redirect-wrapped click-tracking URL for *target_url*."""
    query = urlencode({"to": target_url})
    return f"{base_url.rstrip('/')}/track/click/{quote(notification_id)}?{query}"


__all__ = [
    "TrackingEvent",
    "TrackingRecorder",
    "build_click_tracking_url",
    "build_open_tracking_url",
]
