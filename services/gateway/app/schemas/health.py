"""Payloads returned by the health, readiness, and liveness endpoints."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class HealthStatus(BaseModel):
    """Overall service health snapshot."""

    status: Literal["healthy"]
    service: str
    version: str
    environment: str


class LivenessStatus(BaseModel):
    """Process liveness — the process is running and able to serve traffic."""

    status: Literal["alive"]


class ReadinessCheck(BaseModel):
    """Result of a single readiness dependency check."""

    name: str
    status: Literal["ok", "failed"]


class ReadinessStatus(BaseModel):
    """Aggregate readiness — whether the service is ready to receive traffic."""

    status: Literal["ready", "not_ready"]
    checks: list[ReadinessCheck]
