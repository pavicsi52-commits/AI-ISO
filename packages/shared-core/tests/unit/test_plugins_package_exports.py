"""Tests for __init__.py."""

from __future__ import annotations

import shared_core.plugins as plugins_package


def test_package_exports_are_all_importable() -> None:
    for name in plugins_package.__all__:
        assert hasattr(plugins_package, name)


def test_package_exports_have_no_duplicates() -> None:
    assert len(plugins_package.__all__) == len(set(plugins_package.__all__))
