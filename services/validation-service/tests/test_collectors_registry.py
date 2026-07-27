"""Tests for :class:`app.collectors.registry.CollectorRegistry`."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from shared_core.exceptions.validation import ValidationError

from app.collectors.registry import CollectorRegistry
from app.models.enums import ValidationCheckType, ValidationTargetType
from app.models.validation_check import ValidationCheck
from app.models.validation_target import ValidationTarget


def _check(collector_key: str) -> ValidationCheck:
    return ValidationCheck(
        organization_id=uuid.uuid4(),
        check_type=ValidationCheckType.CUSTOM,
        name="test-check",
        collector_key=collector_key,
    )


def _target() -> ValidationTarget:
    return ValidationTarget(
        organization_id=uuid.uuid4(),
        target_type=ValidationTargetType.CUSTOM_TARGET,
        external_id=str(uuid.uuid4()),
        name="test-target",
    )


class TestCollectorRegistry:
    async def test_unknown_collector_key_raises(self) -> None:
        registry = CollectorRegistry()
        with pytest.raises(ValidationError, match="unknown collector"):
            await registry.collect(_check("does-not-exist"), _target(), None)  # type: ignore[arg-type]

    async def test_register_adds_custom_collector(self) -> None:
        registry = CollectorRegistry()

        async def _custom(check: object, target: object, context: object) -> dict[str, Any]:
            return {"ok": True}

        registry.register("custom", _custom)
        data = await registry.collect(_check("custom"), _target(), None)  # type: ignore[arg-type]
        assert data == {"ok": True}

    async def test_default_collectors_include_network_and_remote(self) -> None:
        registry = CollectorRegistry()
        for key in ("connectivity", "port", "dns", "certificate", "automation_job"):
            assert key in registry._collectors
