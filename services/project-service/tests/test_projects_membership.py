"""Tests for ``app/projects/membership.py`` -- pure rank-comparison logic."""

from __future__ import annotations

import pytest

from app.projects.membership import rank_at_least


@pytest.mark.parametrize(
    ("role_rank", "minimum_rank", "expected"),
    [
        (100, 90, True),
        (90, 90, True),
        (50, 90, False),
        (0, 0, True),
        (10, 50, False),
    ],
)
def test_rank_at_least(role_rank: int, minimum_rank: int, expected: bool) -> None:
    assert rank_at_least(role_rank, minimum_rank) is expected
