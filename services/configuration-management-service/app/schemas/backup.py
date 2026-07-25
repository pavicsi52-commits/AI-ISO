"""Request/response schemas for ``POST /configurations/{id}/backup``."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import BackupStatus, BackupType


class ConfigurationBackupCreateRequest(BaseModel):
    """Body of ``POST /configurations/{id}/backup``."""

    backup_type: BackupType = BackupType.CONFIGURATION_BACKUP
    encrypted: bool = False
    retention_until: datetime | None = None


class ConfigurationBackupResponse(BaseModel):
    """One backup/snapshot/export of a configuration profile's full state."""

    id: UUID
    profile_id: UUID
    backup_type: BackupType
    status: BackupStatus
    checksum: str | None
    encrypted: bool
    retention_until: datetime | None
    created_at: datetime


__all__ = ["ConfigurationBackupCreateRequest", "ConfigurationBackupResponse"]
