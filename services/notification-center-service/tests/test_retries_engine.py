"""Pure tests for app/retries/engine.py -- no database, no fixtures."""

from __future__ import annotations

import pytest
from shared_core.enums.notification_channel import NotificationChannel
from shared_core.notifications.delivery import DeliveryResult, DeliveryStatus, build_delivery_result

from app.retries.engine import compute_delay_seconds, is_dead_letter, should_retry

pytestmark = pytest.mark.asyncio


def _result(status: DeliveryStatus) -> DeliveryResult:
    return build_delivery_result(status=status, channel=NotificationChannel.EMAIL)


class TestComputeDelaySeconds:
    async def test_delay_is_non_negative(self) -> None:
        delay = compute_delay_seconds(1, base_seconds=5.0, max_seconds=60.0)
        assert delay >= 0

    async def test_delay_is_bounded_by_max_plus_base_jitter(self) -> None:
        delay = compute_delay_seconds(1, base_seconds=5.0, max_seconds=60.0)
        assert delay <= 60.0 + 5.0

    async def test_a_late_attempt_is_clamped_near_the_configured_maximum(self) -> None:
        delay = compute_delay_seconds(50, base_seconds=1.0, max_seconds=30.0)
        assert delay <= 31.0

    async def test_first_attempt_delay_is_at_least_the_base_seconds(self) -> None:
        # attempt=1 -> base * multiplier**0 == base, before jitter is added.
        delay = compute_delay_seconds(1, base_seconds=5.0, max_seconds=60.0)
        assert delay >= 5.0


class TestShouldRetry:
    async def test_failed_with_attempts_remaining_is_retryable(self) -> None:
        result = _result(DeliveryStatus.FAILED)
        assert should_retry(result, attempt_number=1, max_attempts=3) is True

    async def test_failed_with_attempts_exhausted_is_not_retryable(self) -> None:
        result = _result(DeliveryStatus.FAILED)
        assert should_retry(result, attempt_number=3, max_attempts=3) is False

    async def test_attempt_ceiling_short_circuits_regardless_of_status(self) -> None:
        result = _result(DeliveryStatus.FAILED)
        assert should_retry(result, attempt_number=5, max_attempts=3) is False

    async def test_cancelled_is_never_retried_even_with_attempts_remaining(self) -> None:
        result = _result(DeliveryStatus.CANCELLED)
        assert should_retry(result, attempt_number=1, max_attempts=3) is False

    async def test_expired_is_never_retried_even_with_attempts_remaining(self) -> None:
        result = _result(DeliveryStatus.EXPIRED)
        assert should_retry(result, attempt_number=1, max_attempts=3) is False


class TestIsDeadLetter:
    async def test_failed_at_or_past_max_attempts_is_a_dead_letter(self) -> None:
        result = _result(DeliveryStatus.FAILED)
        assert is_dead_letter(result, attempt_number=3, max_attempts=3) is True

    async def test_failed_before_max_attempts_is_not_a_dead_letter(self) -> None:
        result = _result(DeliveryStatus.FAILED)
        assert is_dead_letter(result, attempt_number=1, max_attempts=3) is False

    async def test_cancelled_at_max_attempts_is_not_a_dead_letter(self) -> None:
        result = _result(DeliveryStatus.CANCELLED)
        assert is_dead_letter(result, attempt_number=3, max_attempts=3) is False

    async def test_failed_past_max_attempts_is_still_a_dead_letter(self) -> None:
        result = _result(DeliveryStatus.FAILED)
        assert is_dead_letter(result, attempt_number=10, max_attempts=3) is True
