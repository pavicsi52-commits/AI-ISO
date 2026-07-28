"""``alert_routes`` table -- one routing configuration ("ROUTING"
"Support"). ``target_reference`` names the actual destination (a role
name, a user id, a Slack channel, a webhook URL, etc.) generically,
interpreted according to ``target_type``/``channel``;
``configuration`` carries channel-specific extra settings (e.g. a
webhook's own headers). ``severity_filter`` is nullable -- a route
with none set fires for every severity.
"""

from __future__ import annotations

from typing import Any

from shared_core.database.base import BaseModel
from shared_core.enums.severity import Severity
from sqlalchemy import JSON, Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import AlertRouteChannel, RouteTargetType


class AlertRoute(BaseModel):
    """One routing configuration."""

    __tablename__ = "alert_routes"

    name: Mapped[str] = mapped_column(String(255), index=True)
    channel: Mapped[AlertRouteChannel] = mapped_column(String(16), index=True)
    target_type: Mapped[RouteTargetType] = mapped_column(String(16), index=True)
    target_reference: Mapped[str] = mapped_column(String(255))
    configuration: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    severity_filter: Mapped[Severity | None] = mapped_column(String(16), default=None)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


__all__ = ["AlertRoute"]
