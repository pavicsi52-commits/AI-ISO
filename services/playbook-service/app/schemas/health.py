"""Health/readiness/liveness response shapes, per docs/008 (required on every service)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class HealthStatus(BaseModel):
    """Overall service health."""

    status: Literal["healthy", "unhealthy"]
    service: str
    version: str
    environment: str


class LivenessStatus(BaseModel):
    """Whether the process is alive."""

    status: Literal["alive"]


class ReadinessCheck(BaseModel):
    """One individual readiness dependency check."""

    name: str
    status: Literal["ok", "failed"]
    detail: str | None = None


class ReadinessStatus(BaseModel):
    """Whether the service is ready for traffic."""

    status: Literal["ready", "not_ready"]
    checks: list[ReadinessCheck]


__all__ = ["HealthStatus", "LivenessStatus", "ReadinessCheck", "ReadinessStatus"]
