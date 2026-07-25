"""``configuration_backups`` table. Per docs/039 "BACKUP" "Support":
Configuration Backup, Snapshot, Export, Scheduled Backup, Retention
Policies, Integrity Verification, Encryption.

Configuration data is text/JSON, never a large binary blob the way
``services/inventory-service``'s own CSV/Excel/ZIP export files are --
:attr:`content` stores the full snapshot inline rather than via a
MinIO-backed ``StorageWrapper``, keeping this service's infrastructure
footprint to Postgres/Redis/RabbitMQ only.

"Who created this backup" is already
:class:`~shared_core.base.AuditMixin`'s own inherited ``created_by``
column via :class:`~shared_core.database.base.BaseModel` -- no
service-local column redeclares it (a redeclaration would silently
collide with the inherited one, the same column-name-collision class
first found in ``services/discovery-service``'s own
``DiscoverySchedule.is_active`` and again in
``services/asset-management-service``'s own
``AssetSoftware.software_version``).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import BackupStatus, BackupType


class ConfigurationBackup(BaseModel):
    """One backup/snapshot/export of a configuration profile's full state."""

    __tablename__ = "configuration_backups"

    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("configuration_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    backup_type: Mapped[BackupType] = mapped_column(String(24), index=True)
    status: Mapped[BackupStatus] = mapped_column(
        String(16), default=BackupStatus.PENDING, index=True
    )
    content: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    checksum: Mapped[str | None] = mapped_column(String(128), default=None)
    encrypted: Mapped[bool] = mapped_column(Boolean, default=False)
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


__all__ = ["ConfigurationBackup"]
