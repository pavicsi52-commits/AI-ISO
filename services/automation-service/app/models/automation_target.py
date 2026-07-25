"""``automation_targets`` table. Per docs/040 "EXECUTION TARGETS" and
"CONNECTOR INTEGRATION": what an automation job executes against, and
which connector protocol reaches it.

Per docs/040's own SECURITY section ("Secure credential injection"),
:attr:`credential_ref` stores only a
``services/secrets-management-service`` reference id, never a raw
credential. :attr:`inventory_asset_id` is a plain UUID column (not a
real foreign key) referencing ``services/inventory-service``'s own
asset -- not a SQL foreign key, since that table lives in a separate
service's database, the same cross-service-reference shape
``services/asset-management-service``'s own ``inventory_asset_id``
already established, per docs/040 "INVENTORY INTEGRATION".
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ConnectorType, ExecutionTargetType


class AutomationTarget(BaseModel):
    """One execution target an automation job can run against."""

    __tablename__ = "automation_targets"

    name: Mapped[str] = mapped_column(String(255), index=True)
    target_type: Mapped[ExecutionTargetType] = mapped_column(String(32), index=True)
    connector_type: Mapped[ConnectorType] = mapped_column(String(24), index=True)
    address: Mapped[str] = mapped_column(String(512))
    port: Mapped[int | None] = mapped_column(Integer, default=None)
    username: Mapped[str | None] = mapped_column(String(255), default=None)
    credential_ref: Mapped[str | None] = mapped_column(String(255), default=None)
    inventory_asset_id: Mapped[uuid.UUID | None] = mapped_column(default=None, index=True)
    labels: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)


__all__ = ["AutomationTarget"]
