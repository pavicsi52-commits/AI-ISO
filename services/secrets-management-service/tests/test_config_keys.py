"""Tests for ``app/config/keys.py`` and ``app/config/master_key.py``'s
"fail fast on missing key material" behavior.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from shared_core.exceptions.dependency import DependencyError

from app.config.keys import load_public_key
from app.config.master_key import load_master_key


def test_load_public_key_reads_existing_file(tmp_path: Path) -> None:
    key_path = tmp_path / "public.pem"
    key_path.write_text("-----BEGIN PUBLIC KEY-----\nfake\n-----END PUBLIC KEY-----")
    assert load_public_key(str(key_path)).startswith("-----BEGIN PUBLIC KEY-----")


def test_load_public_key_raises_when_missing(tmp_path: Path) -> None:
    with pytest.raises(DependencyError, match="JWT public key not found"):
        load_public_key(str(tmp_path / "does-not-exist.pem"))


def test_load_master_key_reads_and_strips_existing_file(tmp_path: Path) -> None:
    key_path = tmp_path / "master.key"
    key_path.write_text("  a-base64-key-value  \n")
    assert load_master_key(str(key_path)) == "a-base64-key-value"


def test_load_master_key_raises_when_missing(tmp_path: Path) -> None:
    with pytest.raises(DependencyError, match="Master key not found"):
        load_master_key(str(tmp_path / "does-not-exist.key"))
