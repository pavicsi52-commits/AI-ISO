"""Pure tests for app/retry/engine.py -- no database, no fixtures.

`EXPONENTIAL` delegates to `shared_core.queue.retry.compute_backoff_delay`,
which adds `random.uniform(0, base_seconds)` jitter on top of the capped
exponential value -- this suite only asserts the dispatch and the cap, per
this service's own docstring on the module ("don't retest shared_core's own
logic"), never an exact jittered value.
"""

from __future__ import annotations

from app.models.enums import RetryBackoffStrategy
from app.retry.engine import compute_delay, compute_linear_delay, has_attempts_remaining


class TestComputeLinearDelay:
    def test_scales_linearly_with_attempt_number(self) -> None:
        assert compute_linear_delay(1, base_seconds=5, max_seconds=1000) == 5
        assert compute_linear_delay(2, base_seconds=5, max_seconds=1000) == 10
        assert compute_linear_delay(3, base_seconds=5, max_seconds=1000) == 15

    def test_caps_at_max_seconds(self) -> None:
        assert compute_linear_delay(100, base_seconds=5, max_seconds=20) == 20

    def test_exactly_at_the_cap_boundary_returns_the_uncapped_value(self) -> None:
        assert compute_linear_delay(4, base_seconds=5, max_seconds=20) == 20

    def test_zero_attempt_yields_zero_delay(self) -> None:
        assert compute_linear_delay(0, base_seconds=5, max_seconds=20) == 0


class TestComputeDelayLinearDispatch:
    def test_delegates_exactly_to_compute_linear_delay(self) -> None:
        for attempt in (1, 2, 5):
            direct = compute_linear_delay(attempt, base_seconds=3, max_seconds=100)
            via_dispatch = compute_delay(
                attempt, strategy=RetryBackoffStrategy.LINEAR, base_seconds=3, max_seconds=100
            )
            assert via_dispatch == direct

    def test_the_cap_still_applies_through_the_dispatcher(self) -> None:
        result = compute_delay(
            50, strategy=RetryBackoffStrategy.LINEAR, base_seconds=10, max_seconds=25
        )
        assert result == 25


class TestComputeDelayExponentialDispatch:
    def test_result_is_at_least_the_uncapped_pre_jitter_exponential_value(self) -> None:
        # attempt=3, base=2 -> pre-jitter = min(2 * 2**2, max) = 8 (well under the cap)
        result = compute_delay(
            3, strategy=RetryBackoffStrategy.EXPONENTIAL, base_seconds=2, max_seconds=1000
        )
        assert 8 <= result <= 8 + 2

    def test_result_grows_with_attempt_number_before_the_cap(self) -> None:
        low = compute_delay(
            1, strategy=RetryBackoffStrategy.EXPONENTIAL, base_seconds=1, max_seconds=1000
        )
        high = compute_delay(
            6, strategy=RetryBackoffStrategy.EXPONENTIAL, base_seconds=1, max_seconds=1000
        )
        # attempt=1 pre-jitter is 1, attempt=6 pre-jitter is 32 -- jitter (<1) can't close that gap.
        assert high > low

    def test_max_seconds_caps_the_result_within_one_base_seconds_of_jitter(self) -> None:
        # attempt=20, base=5 -> uncapped exponential value is astronomically larger than max.
        result = compute_delay(
            20, strategy=RetryBackoffStrategy.EXPONENTIAL, base_seconds=5, max_seconds=30
        )
        assert 30 <= result <= 30 + 5

    def test_is_not_the_same_dispatch_path_as_linear(self) -> None:
        # Same attempt/base/max under EXPONENTIAL must not equal LINEAR's exact formula
        # (2**(attempt-1) growth vs. attempt*base growth) once they diverge.
        linear = compute_delay(
            5, strategy=RetryBackoffStrategy.LINEAR, base_seconds=2, max_seconds=1000
        )
        exponential = compute_delay(
            5, strategy=RetryBackoffStrategy.EXPONENTIAL, base_seconds=2, max_seconds=1000
        )
        assert linear == 10
        assert exponential >= 32  # min(2 * 2**4, 1000) = 32, plus non-negative jitter


class TestHasAttemptsRemaining:
    def test_below_the_max_has_attempts_remaining(self) -> None:
        assert has_attempts_remaining(2, max_attempts=5) is True

    def test_at_the_max_has_no_attempts_remaining(self) -> None:
        assert has_attempts_remaining(5, max_attempts=5) is False

    def test_above_the_max_has_no_attempts_remaining(self) -> None:
        assert has_attempts_remaining(6, max_attempts=5) is False

    def test_zero_attempts_made_against_a_positive_max_has_attempts_remaining(self) -> None:
        assert has_attempts_remaining(0, max_attempts=1) is True
