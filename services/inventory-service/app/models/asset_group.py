"""``asset_groups`` table. Per docs/036 "GROUPS": Static, Dynamic,
Rule-Based, Location, Application, Environment, Custom Groups.

Static/Location/Application/Environment/Custom groups persist their
membership directly as :attr:`member_asset_ids` (a JSON list of UUID
strings) -- the same deliberate "thin JSON list instead of a join
table" simplification
``services/secrets-management-service/app/models/credential_set.py``
already established for an analogous "named bundle of ids" shape.
Dynamic/Rule-Based groups instead store a :attr:`rule` (a JSON filter
expression evaluated against assets at read time) and leave
:attr:`member_asset_ids` empty -- their membership is never persisted,
by definition of being computed live.
"""

from __future__ import annotations

from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import GroupType


class AssetGroup(BaseModel):
    """One named collection of assets, static or dynamically computed."""

    __tablename__ = "asset_groups"
    __table_args__ = (UniqueConstraint("organization_id", "name", name="uq_asset_group_name"),)

    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(String(2048), default=None)
    group_type: Mapped[GroupType] = mapped_column(String(16), default=GroupType.STATIC, index=True)
    rule: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    member_asset_ids: Mapped[list[str]] = mapped_column(JSON, default=list)


__all__ = ["AssetGroup"]
