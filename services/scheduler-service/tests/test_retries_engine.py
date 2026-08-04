"""Pure tests for app/retries/engine.py -- no database, no fixtures."""

from __future__ import annotations

from app.models.enums import RetryType
from app.retries.engine import compute_delay_seconds, is_dead_letter, should_retry


class TestComputeDelaySeconds:
    def test_fixed_delay_never_grows_across_attempts(self) -> None:
        first = compute_delay_seconds(RetryType.FIXED, 1, base_seconds=10.0, max_seconds=300.0)
        third = compute_delay_seconds(RetryType.FIXED, 3, base_seconds=10.0, max_seconds=300.0)
        assert 10.0 <= first < 20.0
        assert 10.0 <= third < 20.0

    def test_linear_delay_grows_proportionally_to_the_attempt(self) -> None:
        first = compute_delay_seconds(
            RetryType.LINEAR_BACKOFF, 1, base_seconds=10.0, max_seconds=300.0
        )
        third = compute_delay_seconds(
            RetryType.LINEAR_BACKOFF, 3, base_seconds=10.0, max_seconds=300.0
        )
        assert first < third

    def test_linear_delay_is_clamped_to_the_maximum(self) -> None:
        delay = compute_delay_seconds(
            RetryType.LINEAR_BACKOFF, 100, base_seconds=10.0, max_seconds=50.0
        )
        assert delay <= 60.0  # max_seconds plus at most one base_seconds of jitter

    def test_exponential_delay_grows_faster_than_linear(self) -> None:
        exponential_fifth = compute_delay_seconds(
            RetryType.EXPONENTIAL_BACKOFF, 5, base_seconds=1.0, max_seconds=1_000.0
        )
        linear_fifth = compute_delay_seconds(
            RetryType.LINEAR_BACKOFF, 5, base_seconds=1.0, max_seconds=1_000.0
        )
        assert exponential_fifth > linear_fifth

    def test_exponential_delay_is_clamped_to_the_maximum(self) -> None:
        delay = compute_delay_seconds(
            RetryType.EXPONENTIAL_BACKOFF, 50, base_seconds=1.0, max_seconds=30.0
        )
        assert delay <= 31.0

    def test_custom_uses_the_same_curve_as_exponential(self) -> None:
        custom = compute_delay_seconds(RetryType.CUSTOM, 50, base_seconds=1.0, max_seconds=30.0)
        assert custom <= 31.0


class TestShouldRetry:
    def test_retries_on_any_failure_when_no_conditions_are_configured(self) -> None:
        assert should_retry(
            attempt_number=1,
            max_attempts=3,
            exit_code=1,
            error_message="boom",
            retry_conditions={},
        )

    def test_does_not_retry_once_max_attempts_is_reached(self) -> None:
        assert not should_retry(
            attempt_number=3,
            max_attempts=3,
            exit_code=1,
            error_message="boom",
            retry_conditions={},
        )

    def test_retries_only_a_matching_exit_code(self) -> None:
        assert should_retry(
            attempt_number=1,
            max_attempts=3,
            exit_code=2,
            error_message=None,
            retry_conditions={"exit_codes": [1, 2]},
        )

    def test_does_not_retry_a_non_matching_exit_code(self) -> None:
        assert not should_retry(
            attempt_number=1,
            max_attempts=3,
            exit_code=99,
            error_message=None,
            retry_conditions={"exit_codes": [1, 2]},
        )

    def test_retries_a_matching_error_pattern(self) -> None:
        assert should_retry(
            attempt_number=1,
            max_attempts=3,
            exit_code=None,
            error_message="Connection Timeout while dialing",
            retry_conditions={"error_patterns": ["Timeout"]},
        )

    def test_does_not_retry_a_non_matching_error_pattern(self) -> None:
        assert not should_retry(
            attempt_number=1,
            max_attempts=3,
            exit_code=None,
            error_message="Permission denied",
            retry_conditions={"error_patterns": ["Timeout"]},
        )

    def test_does_not_retry_when_a_pattern_is_configured_but_no_error_message_exists(
        self,
    ) -> None:
        assert not should_retry(
            attempt_number=1,
            max_attempts=3,
            exit_code=None,
            error_message=None,
            retry_conditions={"error_patterns": ["Timeout"]},
        )


class TestIsDeadLetter:
    def test_not_dead_letter_before_exhausting_attempts(self) -> None:
        assert not is_dead_letter(attempt_number=1, max_attempts=3, dead_letter_enabled=True)

    def test_dead_letter_once_attempts_are_exhausted(self) -> None:
        assert is_dead_letter(attempt_number=3, max_attempts=3, dead_letter_enabled=True)

    def test_never_dead_letter_when_disabled(self) -> None:
        assert not is_dead_letter(attempt_number=5, max_attempts=3, dead_letter_enabled=False)
