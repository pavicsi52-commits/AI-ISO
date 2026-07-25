"""MinIO client creation."""

from __future__ import annotations

from minio import Minio

from shared_core.config.settings import MinioSettings


def create_minio_client(settings: MinioSettings) -> Minio:
    """Create a MinIO client from settings."""
    return Minio(
        settings.endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_use_ssl,
    )
