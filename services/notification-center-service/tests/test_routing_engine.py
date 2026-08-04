"""Pure tests for app/routing/engine.py -- no database, no fixtures."""

from __future__ import annotations

from datetime import time

import pytest

from app.models.enums import NotificationCategory, NotificationChannelKind, NotificationPriority
from app.routing.engine import (
    PreferenceSnapshot,
    allows,
    is_within_quiet_hours,
    resolve_channels,
    should_defer_for_quiet_hours,
)

pytestmark = pytest.mark.asyncio


class TestAllows:
    async def test_allows_by_default_with_no_restrictions(self) -> None:
        pref = PreferenceSnapshot(user_id="u1")
        assert (
            allows(pref, channel=NotificationChannelKind.EMAIL, category=NotificationCategory.ALERT)
            is True
        )

    async def test_muted_blocks_every_channel_and_category(self) -> None:
        pref = PreferenceSnapshot(user_id="u1", muted=True)
        assert (
            allows(pref, channel=NotificationChannelKind.EMAIL, category=NotificationCategory.ALERT)
            is False
        )

    async def test_unsubscribed_channel_is_blocked(self) -> None:
        pref = PreferenceSnapshot(
            user_id="u1",
            unsubscribed_channels=frozenset({NotificationChannelKind.EMAIL}),
        )
        assert (
            allows(pref, channel=NotificationChannelKind.EMAIL, category=NotificationCategory.ALERT)
            is False
        )

    async def test_a_different_channel_than_the_unsubscribed_one_is_still_allowed(self) -> None:
        pref = PreferenceSnapshot(
            user_id="u1",
            unsubscribed_channels=frozenset({NotificationChannelKind.EMAIL}),
        )
        assert (
            allows(pref, channel=NotificationChannelKind.SMS, category=NotificationCategory.ALERT)
            is True
        )

    async def test_muted_category_is_blocked(self) -> None:
        pref = PreferenceSnapshot(
            user_id="u1",
            muted_categories=frozenset({NotificationCategory.ALERT}),
        )
        assert (
            allows(pref, channel=NotificationChannelKind.EMAIL, category=NotificationCategory.ALERT)
            is False
        )

    async def test_a_different_category_than_the_muted_one_is_still_allowed(self) -> None:
        pref = PreferenceSnapshot(
            user_id="u1",
            muted_categories=frozenset({NotificationCategory.ALERT}),
        )
        assert (
            allows(
                pref, channel=NotificationChannelKind.EMAIL, category=NotificationCategory.INFORMATION
            )
            is True
        )


class TestIsWithinQuietHours:
    async def test_none_start_never_counts_as_quiet_hours(self) -> None:
        pref = PreferenceSnapshot(user_id="u1", quiet_hours_start=None, quiet_hours_end=time(6, 0))
        assert is_within_quiet_hours(pref, time(23, 0)) is False

    async def test_none_end_never_counts_as_quiet_hours(self) -> None:
        pref = PreferenceSnapshot(user_id="u1", quiet_hours_start=time(22, 0), quiet_hours_end=None)
        assert is_within_quiet_hours(pref, time(23, 0)) is False

    async def test_normal_window_contains_a_moment_inside_it(self) -> None:
        pref = PreferenceSnapshot(
            user_id="u1", quiet_hours_start=time(9, 0), quiet_hours_end=time(17, 0)
        )
        assert is_within_quiet_hours(pref, time(12, 0)) is True

    async def test_normal_window_excludes_a_moment_before_it(self) -> None:
        pref = PreferenceSnapshot(
            user_id="u1", quiet_hours_start=time(9, 0), quiet_hours_end=time(17, 0)
        )
        assert is_within_quiet_hours(pref, time(8, 59)) is False

    async def test_normal_window_includes_its_start_boundary(self) -> None:
        pref = PreferenceSnapshot(
            user_id="u1", quiet_hours_start=time(9, 0), quiet_hours_end=time(17, 0)
        )
        assert is_within_quiet_hours(pref, time(9, 0)) is True

    async def test_normal_window_excludes_its_end_boundary(self) -> None:
        pref = PreferenceSnapshot(
            user_id="u1", quiet_hours_start=time(9, 0), quiet_hours_end=time(17, 0)
        )
        assert is_within_quiet_hours(pref, time(17, 0)) is False

    async def test_wraparound_window_contains_a_moment_after_midnight(self) -> None:
        pref = PreferenceSnapshot(
            user_id="u1", quiet_hours_start=time(22, 0), quiet_hours_end=time(6, 0)
        )
        assert is_within_quiet_hours(pref, time(23, 0)) is True

    async def test_wraparound_window_contains_a_moment_before_dawn(self) -> None:
        pref = PreferenceSnapshot(
            user_id="u1", quiet_hours_start=time(22, 0), quiet_hours_end=time(6, 0)
        )
        assert is_within_quiet_hours(pref, time(3, 0)) is True

    async def test_wraparound_window_excludes_a_daytime_moment(self) -> None:
        pref = PreferenceSnapshot(
            user_id="u1", quiet_hours_start=time(22, 0), quiet_hours_end=time(6, 0)
        )
        assert is_within_quiet_hours(pref, time(12, 0)) is False

    async def test_wraparound_window_includes_its_start_boundary(self) -> None:
        pref = PreferenceSnapshot(
            user_id="u1", quiet_hours_start=time(22, 0), quiet_hours_end=time(6, 0)
        )
        assert is_within_quiet_hours(pref, time(22, 0)) is True

    async def test_wraparound_window_excludes_its_end_boundary(self) -> None:
        pref = PreferenceSnapshot(
            user_id="u1", quiet_hours_start=time(22, 0), quiet_hours_end=time(6, 0)
        )
        assert is_within_quiet_hours(pref, time(6, 0)) is False


class TestShouldDeferForQuietHours:
    async def test_critical_priority_never_defers_even_inside_quiet_hours(self) -> None:
        pref = PreferenceSnapshot(
            user_id="u1", quiet_hours_start=time(22, 0), quiet_hours_end=time(6, 0)
        )
        assert (
            should_defer_for_quiet_hours(
                pref, priority=NotificationPriority.CRITICAL, now=time(23, 0)
            )
            is False
        )

    async def test_high_priority_never_defers_even_inside_quiet_hours(self) -> None:
        pref = PreferenceSnapshot(
            user_id="u1", quiet_hours_start=time(22, 0), quiet_hours_end=time(6, 0)
        )
        assert (
            should_defer_for_quiet_hours(pref, priority=NotificationPriority.HIGH, now=time(23, 0))
            is False
        )

    async def test_normal_priority_defers_when_inside_quiet_hours(self) -> None:
        pref = PreferenceSnapshot(
            user_id="u1", quiet_hours_start=time(22, 0), quiet_hours_end=time(6, 0)
        )
        assert (
            should_defer_for_quiet_hours(pref, priority=NotificationPriority.NORMAL, now=time(23, 0))
            is True
        )

    async def test_normal_priority_does_not_defer_when_outside_quiet_hours(self) -> None:
        pref = PreferenceSnapshot(
            user_id="u1", quiet_hours_start=time(22, 0), quiet_hours_end=time(6, 0)
        )
        assert (
            should_defer_for_quiet_hours(pref, priority=NotificationPriority.NORMAL, now=time(12, 0))
            is False
        )

    async def test_low_priority_defers_when_inside_quiet_hours(self) -> None:
        pref = PreferenceSnapshot(
            user_id="u1", quiet_hours_start=time(9, 0), quiet_hours_end=time(17, 0)
        )
        assert (
            should_defer_for_quiet_hours(pref, priority=NotificationPriority.LOW, now=time(10, 0))
            is True
        )

    async def test_defers_unconditionally_to_is_within_quiet_hours_when_unset(self) -> None:
        pref = PreferenceSnapshot(user_id="u1")
        assert (
            should_defer_for_quiet_hours(pref, priority=NotificationPriority.NORMAL, now=time(23, 0))
            is False
        )


class TestResolveChannels:
    async def test_explicit_requested_channel_is_returned_when_allowed(self) -> None:
        pref = PreferenceSnapshot(user_id="u1")
        result = resolve_channels(
            pref,
            category=NotificationCategory.ALERT,
            requested_channel=NotificationChannelKind.EMAIL,
        )
        assert result == [NotificationChannelKind.EMAIL]

    async def test_explicit_requested_channel_is_never_substituted_when_disallowed(self) -> None:
        pref = PreferenceSnapshot(
            user_id="u1",
            unsubscribed_channels=frozenset({NotificationChannelKind.EMAIL}),
            preferred_channels=(NotificationChannelKind.SMS,),
        )
        result = resolve_channels(
            pref,
            category=NotificationCategory.ALERT,
            requested_channel=NotificationChannelKind.EMAIL,
        )
        assert result == []

    async def test_filters_preferred_channels_by_allows_when_no_requested_channel(self) -> None:
        pref = PreferenceSnapshot(
            user_id="u1",
            preferred_channels=(
                NotificationChannelKind.EMAIL,
                NotificationChannelKind.SMS,
                NotificationChannelKind.SLACK,
            ),
            unsubscribed_channels=frozenset({NotificationChannelKind.SMS}),
        )
        result = resolve_channels(pref, category=NotificationCategory.ALERT)
        assert result == [NotificationChannelKind.EMAIL, NotificationChannelKind.SLACK]

    async def test_no_channel_priority_preserves_the_original_preferred_order(self) -> None:
        pref = PreferenceSnapshot(
            user_id="u1",
            preferred_channels=(NotificationChannelKind.SLACK, NotificationChannelKind.EMAIL),
        )
        result = resolve_channels(pref, category=NotificationCategory.ALERT)
        assert result == [NotificationChannelKind.SLACK, NotificationChannelKind.EMAIL]

    async def test_sorts_allowed_channels_by_channel_priority(self) -> None:
        pref = PreferenceSnapshot(
            user_id="u1",
            preferred_channels=(NotificationChannelKind.EMAIL, NotificationChannelKind.SLACK),
            channel_priority=(NotificationChannelKind.SLACK, NotificationChannelKind.EMAIL),
        )
        result = resolve_channels(pref, category=NotificationCategory.ALERT)
        assert result == [NotificationChannelKind.SLACK, NotificationChannelKind.EMAIL]

    async def test_channels_absent_from_channel_priority_sort_after_ranked_ones(self) -> None:
        pref = PreferenceSnapshot(
            user_id="u1",
            preferred_channels=(
                NotificationChannelKind.EMAIL,
                NotificationChannelKind.SMS,
                NotificationChannelKind.SLACK,
            ),
            channel_priority=(NotificationChannelKind.SLACK, NotificationChannelKind.EMAIL),
        )
        result = resolve_channels(pref, category=NotificationCategory.ALERT)
        # SMS has no entry in channel_priority, so it sorts after every ranked channel.
        assert result == [
            NotificationChannelKind.SLACK,
            NotificationChannelKind.EMAIL,
            NotificationChannelKind.SMS,
        ]
