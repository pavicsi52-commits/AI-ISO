"""``api_routes`` -- one routing rule.

Ordered by :attr:`ApiRoute.priority` (lower evaluated first) within an
organization; :mod:`app.routing.engine` is the pure function that walks
a caller's own routes in that order and picks the first match, falling
back to any route with ``match_kind == FALLBACK`` if nothing else
matched.
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import RouteMatchKind


class ApiRoute(BaseModel):
    """``api_routes`` -- one routing rule directing matching requests to one service."""

    __tablename__ = "api_routes"
    __table_args__ = (
        Index("ix_api_route_org_priority", "organization_id", "priority"),
        Index("ix_api_route_org_service", "organization_id", "service_id"),
    )

    service_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("api_services.id", ondelete="CASCADE"), index=True
    )
    version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("api_versions.id", ondelete="SET NULL"), default=None, index=True
    )

    name: Mapped[str] = mapped_column(String(128))
    match_kind: Mapped[RouteMatchKind] = mapped_column(
        String(32), default=RouteMatchKind.PATH, index=True
    )

    path_pattern: Mapped[str] = mapped_column(String(512))
    """A glob-shaped pattern (``*`` one segment, ``**`` any depth), matched by
    :func:`app.routing.engine.path_matches`."""

    host_pattern: Mapped[str | None] = mapped_column(String(255), default=None)
    methods: Mapped[list[str]] = mapped_column(JSON, default=list)
    """Empty means "any method"."""

    header_match: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    """Header name -> required value, for ``match_kind == HEADER``."""

    weight: Mapped[int] = mapped_column(Integer, default=100)
    """This route's own share of traffic among every other route with the
    same ``path_pattern`` for ``match_kind == WEIGHTED``."""

    priority: Mapped[int] = mapped_column(Integer, default=100, index=True)
    """Lower evaluates first."""

    strip_prefix: Mapped[bool] = mapped_column(Boolean, default=False)
    rewrite_path: Mapped[str | None] = mapped_column(String(512), default=None)

    requires_auth: Mapped[bool] = mapped_column(Boolean, default=True)
    allowed_auth_methods: Mapped[list[str]] = mapped_column(JSON, default=list)
    """Empty means "any configured method is accepted"."""

    required_scopes: Mapped[list[str]] = mapped_column(JSON, default=list)
    required_permission: Mapped[str | None] = mapped_column(String(128), default=None)

    is_fallback: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


__all__ = ["ApiRoute"]
