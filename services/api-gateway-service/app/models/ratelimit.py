"""``api_rate_limits`` -- one configured rate-limit policy."""

from __future__ import annotations

from shared_core.database.base import BaseModel
from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import RateLimitAlgorithm, RateLimitScope


class ApiRateLimitPolicy(BaseModel):
    """``api_rate_limits`` -- one policy, scoped to a global/org/project/user/key/endpoint."""

    __tablename__ = "api_rate_limits"

    scope: Mapped[RateLimitScope] = mapped_column(String(16), index=True)
    scope_reference: Mapped[str | None] = mapped_column(String(255), default=None, index=True)
    """The specific org id / project id / user id / api key id / endpoint
    pattern this policy applies to -- ``None`` for ``scope == GLOBAL``."""

    algorithm: Mapped[RateLimitAlgorithm] = mapped_column(
        String(16), default=RateLimitAlgorithm.SLIDING_WINDOW
    )
    max_requests: Mapped[int] = mapped_column(Integer)
    window_seconds: Mapped[int] = mapped_column(Integer)
    burst_max_requests: Mapped[int | None] = mapped_column(Integer, default=None)
    burst_window_seconds: Mapped[int | None] = mapped_column(Integer, default=None)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


__all__ = ["ApiRateLimitPolicy"]
