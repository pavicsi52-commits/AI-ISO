"""Tests for :class:`app.collectors.registry.CollectorRegistry`."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from shared_core.exceptions.validation import ValidationError

from app.collectors.registry import CollectorRegistry
from app.models.enums import MonitoringTargetType
from app.models.monitoring_collector import MonitoringCollector
from app.models.monitoring_target import MonitoringTarget


def _collector(collector_key: str) -> MonitoringCollector:
    return MonitoringCollector(
        organization_id=uuid.uuid4(), name="test-collector", collector_key=collector_key
    )


def _target() -> MonitoringTarget:
    return MonitoringTarget(
        organization_id=uuid.uuid4(),
        target_type=MonitoringTargetType.CUSTOM_TARGET,
        external_id=str(uuid.uuid4()),
        name="test-target",
    )


class TestCollectorRegistry:
    async def test_unknown_collector_key_raises(self) -> None:
        registry = CollectorRegistry()
        with pytest.raises(ValidationError, match="unknown collector_key"):
            await registry.collect(_collector("does-not-exist"), _target(), None)  # type: ignore[arg-type]

    async def test_register_adds_custom_collector(self) -> None:
        registry = CollectorRegistry()

        async def _custom(collector: object, target: object, context: object) -> dict[str, Any]:
            return {"ok": True}

        registry.register("custom", _custom)
        data = await registry.collect(_collector("custom"), _target(), None)  # type: ignore[arg-type]
        assert data == {"ok": True}

    async def test_default_collectors_include_network_and_remote(self) -> None:
        registry = CollectorRegistry()
        for key in ("connectivity", "port", "dns", "certificate", "http", "automation_job"):
            assert key in registry._collectors
