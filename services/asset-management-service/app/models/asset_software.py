"""``asset_software`` table. Per docs/038 "SOFTWARE MANAGEMENT"
"Track": Installed Software, Versions, Licenses, Patches, Security
Updates, End-of-Life Status, Software Inventory. One row per software
item installed on a managed asset; patch/security-update events
against a given item are recorded in
:mod:`app.models.asset_patch_history`.

:attr:`software_version` (not ``version``) -- ``version`` is already
:class:`~shared_core.base.VersionMixin`'s own optimistic-concurrency
counter, inherited via :class:`~shared_core.database.base.BaseModel`;
redeclaring it here would silently repurpose that column, the same
column-name collision class that previously hit
``discovery-service``'s ``DiscoverySchedule.is_active`` against
``BaseModel``'s own soft-delete ``is_active``.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import SoftwareEndOfLifeStatus


class AssetSoftware(BaseModel):
    """One installed software item on a managed asset."""

    __tablename__ = "asset_software"

    managed_asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("managed_assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), index=True)
    software_version: Mapped[str | None] = mapped_column(String(64), default=None)
    license_key: Mapped[str | None] = mapped_column(String(255), default=None)
    end_of_life_status: Mapped[SoftwareEndOfLifeStatus] = mapped_column(
        String(16), default=SoftwareEndOfLifeStatus.UNKNOWN
    )
    installed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


__all__ = ["AssetSoftware"]
