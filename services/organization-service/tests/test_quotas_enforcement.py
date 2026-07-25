"""Tests for ``app/quotas/enforcement.py`` -- pure quota comparison logic."""

from __future__ import annotations

import pytest

from app.quotas.enforcement import check_quota


@pytest.mark.parametrize(
    ("current", "maximum", "expected_within", "expected_remaining"),
    [
        (0, 10, True, 10),
        (5, 10, True, 5),
        (9, 10, True, 1),
        (10, 10, False, 0),
        (11, 10, False, 0),
    ],
)
def test_check_quota_bounded(
    current: int, maximum: int, expected_within: bool, expected_remaining: int
) -> None:
    result = check_quota(current=current, maximum=maximum)
    assert result.within_quota is expected_within
    assert result.current == current
    assert result.maximum == maximum
    assert result.remaining == expected_remaining


@pytest.mark.parametrize("maximum", [0, -1, -100])
def test_check_quota_unlimited_when_maximum_not_positive(maximum: int) -> None:
    result = check_quota(current=1_000_000, maximum=maximum)
    assert result.within_quota is True
    assert result.remaining == 0
