"""Tests that shared_core.utils re-exports shared_core.helpers."""

from __future__ import annotations

from shared_core import helpers, utils


def test_utils_reexports_the_same_functions_as_helpers() -> None:
    assert set(utils.__all__) == set(helpers.__all__)


def test_utils_slugify_is_the_same_function_as_helpers_slugify() -> None:
    assert utils.slugify is helpers.slugify
