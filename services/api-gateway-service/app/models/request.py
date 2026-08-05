"""``api_requests`` and ``api_responses`` -- one proxied call's own full record."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import AuthenticationMethod


class ApiRequestLog(BaseModel):
    """``api_requests`` -- one inbound request the gateway received."""

    __tablename__ = "api_requests"
    __table_args__ = (
        Index("ix_api_request_org_started", "organization_id", "started_at"),
        Index("ix_api_request_org_client", "organization_id", "client_id"),
    )

    client_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("api_clients.id", ondelete="SET NULL"), default=None, index=True
    )
    api_key_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("api_keys.id", ondelete="SET NULL"), default=None, index=True
    )
    route_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("api_routes.id", ondelete="SET NULL"), default=None, index=True
    )
    service_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("api_services.id", ondelete="SET NULL"), default=None, index=True
    )

    method: Mapped[str] = mapped_column(String(16))
    path: Mapped[str] = mapped_column(String(1024))
    query_string: Mapped[str | None] = mapped_column(String(2048), default=None)
    correlation_id: Mapped[str] = mapped_column(String(64), index=True)

    source_ip: Mapped[str | None] = mapped_column(String(64), default=None)
    user_agent: Mapped[str | None] = mapped_column(String(512), default=None)
    authenticated_user_id: Mapped[str | None] = mapped_column(String(255), default=None)
    auth_method: Mapped[AuthenticationMethod | None] = mapped_column(String(32), default=None)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    request_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ApiResponseLog(BaseModel):
    """``api_responses`` -- one request's own outcome."""

    __tablename__ = "api_responses"
    __table_args__ = (Index("ix_api_response_org_request", "organization_id", "request_id"),)

    request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("api_requests.id", ondelete="CASCADE"), index=True
    )
    status_code: Mapped[int] = mapped_column(Integer, index=True)
    upstream_instance: Mapped[str | None] = mapped_column(String(255), default=None)

    latency_ms: Mapped[float] = mapped_column(Float)
    upstream_latency_ms: Mapped[float | None] = mapped_column(Float, default=None)

    error: Mapped[str | None] = mapped_column(Text, default=None)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False)
    circuit_breaker_tripped: Mapped[bool] = mapped_column(Boolean, default=False)
    rate_limited: Mapped[bool] = mapped_column(Boolean, default=False)
    quota_exceeded: Mapped[bool] = mapped_column(Boolean, default=False)


__all__ = ["ApiRequestLog", "ApiResponseLog"]
