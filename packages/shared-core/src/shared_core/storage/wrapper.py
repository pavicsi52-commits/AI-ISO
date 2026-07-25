"""MinIO object storage wrapper.

The only place any AI-IOS service talks to MinIO directly, per
docs/012_Shared_Core_Framework.md.txt "STORAGE". Files are never stored
locally by any service (docs/008_Backend_Master_Architecture.md.txt
"FILES").

The official ``minio`` SDK is synchronous; every method here runs it via
``asyncio.to_thread`` so it never blocks the event loop
(docs/005_Coding_Standards_Master.md.txt "CONCURRENCY").
"""

from __future__ import annotations

import asyncio
import io
from datetime import timedelta

from minio import Minio
from minio.error import S3Error

from shared_core.exceptions.dependency import DependencyError
from shared_core.exceptions.not_found import NotFoundError


class StorageWrapper:
    """Async-friendly wrapper around a MinIO client."""

    def __init__(self, client: Minio) -> None:
        self._client = client

    async def ensure_bucket(self, bucket: str) -> None:
        """Create ``bucket`` if it does not already exist."""

        def _ensure() -> None:
            if not self._client.bucket_exists(bucket):
                self._client.make_bucket(bucket)

        await asyncio.to_thread(_ensure)

    async def upload(self, bucket: str, key: str, data: bytes, content_type: str) -> str:
        """Upload ``data`` to ``bucket``/``key`` and return the key."""

        def _upload() -> None:
            self._client.put_object(
                bucket, key, io.BytesIO(data), length=len(data), content_type=content_type
            )

        try:
            await asyncio.to_thread(_upload)
        except S3Error as exc:
            raise DependencyError(f"Failed to upload '{key}' to bucket '{bucket}'.") from exc
        return key

    async def download(self, bucket: str, key: str) -> bytes:
        """Download and return the raw bytes at ``bucket``/``key``."""

        def _download() -> bytes:
            response = self._client.get_object(bucket, key)
            try:
                return response.read()
            finally:
                response.close()
                response.release_conn()

        try:
            return await asyncio.to_thread(_download)
        except S3Error as exc:
            if exc.code == "NoSuchKey":
                raise NotFoundError(f"Object '{key}' was not found in bucket '{bucket}'.") from exc
            raise DependencyError(f"Failed to download '{key}' from bucket '{bucket}'.") from exc

    async def delete(self, bucket: str, key: str) -> None:
        """Delete the object at ``bucket``/``key``."""
        try:
            await asyncio.to_thread(self._client.remove_object, bucket, key)
        except S3Error as exc:
            raise DependencyError(f"Failed to delete '{key}' from bucket '{bucket}'.") from exc

    async def exists(self, bucket: str, key: str) -> bool:
        """Return whether an object exists at ``bucket``/``key``."""

        def _stat() -> bool:
            try:
                self._client.stat_object(bucket, key)
                return True
            except S3Error as exc:
                if exc.code == "NoSuchKey":
                    return False
                raise

        try:
            return await asyncio.to_thread(_stat)
        except S3Error as exc:
            raise DependencyError(f"Failed to check existence of '{key}'.") from exc

    async def presigned_url(self, bucket: str, key: str, expires_seconds: int) -> str:
        """Return a time-limited URL for downloading ``bucket``/``key`` directly."""
        try:
            return await asyncio.to_thread(
                self._client.presigned_get_object,
                bucket,
                key,
                expires=timedelta(seconds=expires_seconds),
            )
        except S3Error as exc:
            raise DependencyError(f"Failed to generate presigned URL for '{key}'.") from exc
