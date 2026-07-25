"""``configuration_profiles`` table -- the profile root entity.

Per docs/039 "CONFIGURATION PROFILE MODEL": Configuration ID,
Organization ID, Project ID, Profile Name, Description, Version,
Status, Environment, Owner, Configuration Type, Target Assets,
Variables, Tags, Metadata, Created At, Updated At.

:attr:`profile_version` (not ``version``) -- ``version`` is already
:class:`~shared_core.base.VersionMixin`'s own optimistic-concurrency
counter, inherited via :class:`~shared_core.database.base.BaseModel`;
redeclaring it here would silently repurpose that column, the same
column-name collision class previously hit by
``services/asset-management-service``'s own
``AssetSoftware.software_version``.

``target_assets``/``tags`` are JSON columns here rather than dedicated
join tables -- docs/039's own 22-table DATABASE TABLES list names no
``configuration_profile_targets``/``configuration_tags`` table, unlike
``services/inventory-service``'s own tag/label split (which docs/036
explicitly required for independent filtering); per-asset assignment
*status* tracking (active/pending/failed) instead lives in the
dedicated ``configuration_assignments`` table.
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ConfigurationType, EnvironmentType, ProfileStatus


class ConfigurationProfile(BaseModel):
    """One configuration profile: the authoritative desired state for a
    configuration type/environment combination.
    """

    __tablename__ = "configuration_profiles"

    profile_name: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(String(2048), default=None)
    profile_version: Mapped[str] = mapped_column(String(32), default="1.0.0")
    status: Mapped[ProfileStatus] = mapped_column(
        String(24), default=ProfileStatus.DRAFT, index=True
    )
    environment: Mapped[EnvironmentType] = mapped_column(String(24), index=True)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    configuration_type: Mapped[ConfigurationType] = mapped_column(String(24), index=True)
    target_assets: Mapped[list[str]] = mapped_column(JSON, default=list)
    variables: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)


__all__ = ["ConfigurationProfile"]
