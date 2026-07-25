"""``discovery_targets`` table -- one addressable thing to probe.

Per docs/037 "DISCOVERY TARGETS": a target names *where* to probe (a
host, a subnet/CIDR, a cloud account, a Kubernetes cluster, an
industrial network) and *how* (:class:`~app.models.enums.ProtocolType`
plus an optional port), with an optional
:class:`~app.models.discovery_credential.DiscoveryCredential` reference
for authenticated protocols.

:attr:`is_enabled` (not ``is_active``) -- see
``app/models/discovery_filter.py``'s own docstring for the
column-name-collision class this avoids.
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ProtocolType, TargetType


class DiscoveryTarget(BaseModel):
    """One addressable target for discovery protocol probes."""

    __tablename__ = "discovery_targets"

    profile_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("discovery_profiles.id", ondelete="SET NULL"), default=None
    )
    target_type: Mapped[TargetType] = mapped_column(String(24), index=True)
    address: Mapped[str] = mapped_column(String(255), index=True)
    protocol: Mapped[ProtocolType] = mapped_column(String(16), index=True)
    port: Mapped[int | None] = mapped_column(Integer, default=None)
    credential_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("discovery_credentials.id", ondelete="SET NULL"), default=None
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)


__all__ = ["DiscoveryTarget"]
