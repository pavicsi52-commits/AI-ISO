"""Tests for ``app.packages.engine``: ``build_package``/``extract_package``/
``compute_package_checksum``/``PackagingError``.

No infrastructure needed -- everything is built and read back in memory
against real ``tarfile``/``zipfile`` archives, never mocked.
"""

from __future__ import annotations

import hashlib

import pytest

from app.models.enums import PackageFormat
from app.packages.engine import (
    PackagingError,
    build_package,
    compute_package_checksum,
    extract_package,
)

_FORMATS = (PackageFormat.TAR_GZ, PackageFormat.ZIP)


# ---- round trips ----------------------------------------------------------------


@pytest.mark.parametrize("package_format", _FORMATS)
def test_single_file_round_trips_byte_for_byte(package_format: PackageFormat) -> None:
    files = {"manifest.json": b'{"name": "test-plugin"}'}
    package_bytes = build_package(files, package_format=package_format)
    extracted = extract_package(package_bytes, package_format=package_format)
    assert extracted == files


@pytest.mark.parametrize("package_format", _FORMATS)
def test_multi_file_round_trips_byte_for_byte(package_format: PackageFormat) -> None:
    files = {
        "manifest.json": b'{"name": "test-plugin", "version": "1.0.0"}',
        "src/main.py": b"def run():\n    return 42\n",
        "README.md": b"# Test Plugin\n\nDoes things.\n",
        "assets/icon.png": bytes(range(256)),  # arbitrary binary content
    }
    package_bytes = build_package(files, package_format=package_format)
    extracted = extract_package(package_bytes, package_format=package_format)
    assert extracted == files
    for path, content in files.items():
        assert extracted[path] == content


@pytest.mark.parametrize("package_format", _FORMATS)
def test_many_file_archive_round_trips_byte_for_byte(package_format: PackageFormat) -> None:
    files = {f"module_{index:02d}.py": f"VALUE = {index}\n".encode() for index in range(15)}
    package_bytes = build_package(files, package_format=package_format)
    extracted = extract_package(package_bytes, package_format=package_format)
    assert extracted == files
    assert len(extracted) == 15


@pytest.mark.parametrize("package_format", _FORMATS)
def test_nested_paths_are_preserved(package_format: PackageFormat) -> None:
    files = {
        "src/plugin/handlers/inventory.py": b"# handler",
        "src/plugin/handlers/__init__.py": b"",
        "src/plugin/__init__.py": b"",
    }
    package_bytes = build_package(files, package_format=package_format)
    extracted = extract_package(package_bytes, package_format=package_format)
    assert extracted == files


@pytest.mark.parametrize("package_format", _FORMATS)
def test_empty_file_content_round_trips(package_format: PackageFormat) -> None:
    files = {"empty.txt": b"", "nonempty.txt": b"content"}
    package_bytes = build_package(files, package_format=package_format)
    extracted = extract_package(package_bytes, package_format=package_format)
    assert extracted == files


# ---- empty file set --------------------------------------------------------------


@pytest.mark.parametrize("package_format", _FORMATS)
def test_building_empty_file_set_raises_packaging_error(package_format: PackageFormat) -> None:
    with pytest.raises(PackagingError):
        build_package({}, package_format=package_format)


# ---- corrupt archives -------------------------------------------------------------


@pytest.mark.parametrize("package_format", _FORMATS)
def test_extracting_garbage_bytes_raises_packaging_error(package_format: PackageFormat) -> None:
    with pytest.raises(PackagingError):
        extract_package(b"this is definitely not a valid archive", package_format=package_format)


@pytest.mark.parametrize("package_format", _FORMATS)
def test_extracting_empty_bytes_raises_packaging_error(package_format: PackageFormat) -> None:
    with pytest.raises(PackagingError):
        extract_package(b"", package_format=package_format)


def test_extracting_a_zip_archive_as_tar_gz_raises_packaging_error() -> None:
    zip_bytes = build_package({"a.txt": b"a"}, package_format=PackageFormat.ZIP)
    with pytest.raises(PackagingError):
        extract_package(zip_bytes, package_format=PackageFormat.TAR_GZ)


def test_extracting_a_tar_gz_archive_as_zip_raises_packaging_error() -> None:
    tar_bytes = build_package({"a.txt": b"a"}, package_format=PackageFormat.TAR_GZ)
    with pytest.raises(PackagingError):
        extract_package(tar_bytes, package_format=PackageFormat.ZIP)


# ---- checksum ----------------------------------------------------------------------


def test_checksum_matches_raw_sha256_of_the_bytes() -> None:
    payload = b"some packaged artifact bytes"
    assert compute_package_checksum(payload) == hashlib.sha256(payload).hexdigest()


def test_checksum_is_deterministic_for_the_same_bytes() -> None:
    payload = b"identical bytes"
    assert compute_package_checksum(payload) == compute_package_checksum(payload)


def test_checksum_differs_for_different_content() -> None:
    package_a = build_package({"a.txt": b"content A"}, package_format=PackageFormat.ZIP)
    package_b = build_package({"a.txt": b"content B"}, package_format=PackageFormat.ZIP)
    assert compute_package_checksum(package_a) != compute_package_checksum(package_b)


def test_checksum_differs_for_different_file_sets_even_at_same_size() -> None:
    package_a = build_package({"a.txt": b"xxxxxxxxxx"}, package_format=PackageFormat.TAR_GZ)
    package_b = build_package({"b.txt": b"xxxxxxxxxx"}, package_format=PackageFormat.TAR_GZ)
    assert compute_package_checksum(package_a) != compute_package_checksum(package_b)


def test_checksum_is_a_64_character_hex_digest() -> None:
    package_bytes = build_package({"a.txt": b"a"}, package_format=PackageFormat.ZIP)
    checksum = compute_package_checksum(package_bytes)
    assert len(checksum) == 64
    assert all(char in "0123456789abcdef" for char in checksum)
