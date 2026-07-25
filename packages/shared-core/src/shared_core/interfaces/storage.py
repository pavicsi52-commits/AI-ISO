"""Object storage interface.

Concrete implementation is the MinIO wrapper in ``shared_core.storage``.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class StorageProtocol(Protocol):
    """Structural interface for object storage."""

    async def upload(self, bucket: str, key: str, data: bytes, content_type: str) -> str:
        """Upload an object and return its storage key."""
        ...

    async def download(self, bucket: str, key: str) -> bytes:
        """Download and return an object's raw bytes."""
        ...

    async def delete(self, bucket: str, key: str) -> None:
        """Delete an object."""
        ...

    async def presigned_url(self, bucket: str, key: str, expires_seconds: int) -> str:
        """Return a time-limited URL for downloading an object directly."""
        ...
