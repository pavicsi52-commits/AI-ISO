"""Tests for :func:`app.config.keys.load_public_key`."""

from __future__ import annotations

import pytest
from shared_core.exceptions.dependency import DependencyError

from app.config.keys import load_public_key


def test_load_public_key_missing_file_raises() -> None:
    with pytest.raises(DependencyError):
        load_public_key("/nonexistent/path/public.pem")
