"""Schemas for lifecycle actions and the underlying change-history/
retirement records -- per docs/038 "LIFECYCLE MANAGEMENT": Provision,
Operate, Maintain, Upgrade, Reassign, Retire, Archive, Dispose,
Lifecycle Audit.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import LifecycleState


class LifecycleActionRequest(BaseModel):
    """Body of a lifecycle-transition request (used internally by the
    :class:`~app.services.lifecycle.LifecycleService` action helpers,
    not its own top-level REST endpoint -- docs/038's REST APIs list
    drives lifecycle transitions through ``PATCH /assets/{id}``).
    """

    target_state: LifecycleState
    reason: str | None = None


class AssetChangeHistoryResponse(BaseModel):
    """One narrative timeline entry."""

    id: UUID
    managed_asset_id: UUID
    actor_id: UUID | None
    event_type: str
    detail: dict[str, Any]
    created_at: datetime


class AssetRetirementResponse(BaseModel):
    """One managed asset's retirement and disposal record."""

    id: UUID
    managed_asset_id: UUID
    retired_at: datetime
    retired_by: UUID | None
    reason: str | None
    disposed_at: datetime | None
    disposal_method: str | None
    residual_value_realized: float | None


__all__ = ["AssetChangeHistoryResponse", "AssetRetirementResponse", "LifecycleActionRequest"]
