"""MinIO object storage framework: upload, download, delete, presigned URL."""

from shared_core.storage.client import create_minio_client
from shared_core.storage.wrapper import StorageWrapper

__all__ = ["StorageWrapper", "create_minio_client"]
