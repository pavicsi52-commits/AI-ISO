"""Tests for the MinIO storage framework.

Runs against the real MinIO started by the repository's
``docker-compose.yml`` (Phase 1). Skipped automatically if unreachable
(see the ``storage`` fixture in conftest.py).
"""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions import NotFoundError
from shared_core.storage import StorageWrapper

BUCKET = "test-bucket"


def _unique_key() -> str:
    return f"test/{uuid.uuid4().hex}.txt"


async def test_upload_and_download_round_trip(storage: StorageWrapper) -> None:
    key = _unique_key()
    data = b"hello world"

    await storage.upload(BUCKET, key, data, "text/plain")
    downloaded = await storage.download(BUCKET, key)

    assert downloaded == data


async def test_upload_returns_the_key(storage: StorageWrapper) -> None:
    key = _unique_key()

    result = await storage.upload(BUCKET, key, b"data", "text/plain")

    assert result == key


async def test_exists_reflects_uploaded_objects(storage: StorageWrapper) -> None:
    key = _unique_key()

    assert await storage.exists(BUCKET, key) is False

    await storage.upload(BUCKET, key, b"data", "text/plain")

    assert await storage.exists(BUCKET, key) is True


async def test_delete_removes_the_object(storage: StorageWrapper) -> None:
    key = _unique_key()
    await storage.upload(BUCKET, key, b"data", "text/plain")

    await storage.delete(BUCKET, key)

    assert await storage.exists(BUCKET, key) is False


async def test_download_raises_not_found_for_missing_object(storage: StorageWrapper) -> None:
    with pytest.raises(NotFoundError):
        await storage.download(BUCKET, _unique_key())


async def test_presigned_url_returns_a_url(storage: StorageWrapper) -> None:
    key = _unique_key()
    await storage.upload(BUCKET, key, b"data", "text/plain")

    url = await storage.presigned_url(BUCKET, key, expires_seconds=60)

    assert url.startswith("http")
    assert key in url
