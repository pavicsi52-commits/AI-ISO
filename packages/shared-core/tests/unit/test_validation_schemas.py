"""Tests for validation-framework schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from shared_core.validation.schemas import (
    ConnectorConfigSchema,
    WorkflowEdgeSchema,
    WorkflowNodeSchema,
)


def test_workflow_node_schema_defaults() -> None:
    node = WorkflowNodeSchema(id="node-1", type="task")

    assert node.required_inputs == []
    assert node.is_destructive is False
    assert node.supports_rollback is False
    assert node.max_iterations is None


def test_workflow_node_schema_accepts_full_fields() -> None:
    node = WorkflowNodeSchema(
        id="loop-1",
        type="loop",
        max_iterations=10,
        required_inputs=["input_a"],
        timeout_seconds=60,
        is_destructive=True,
        supports_rollback=True,
    )

    assert node.max_iterations == 10
    assert node.required_inputs == ["input_a"]


def test_workflow_node_schema_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        WorkflowNodeSchema(id="node-1", type="task", unexpected_field="x")


def test_workflow_edge_schema() -> None:
    edge = WorkflowEdgeSchema(source="a", target="b")

    assert edge.source == "a"
    assert edge.target == "b"


def test_connector_config_schema_defaults() -> None:
    config = ConnectorConfigSchema(host="1.2.3.4", version="1.0")

    assert config.timeout_seconds == 30
    assert config.capabilities == []
    assert config.certificate is None


def test_connector_config_schema_accepts_full_fields() -> None:
    config = ConnectorConfigSchema(
        host="1.2.3.4",
        timeout_seconds=60,
        version="2.0",
        capabilities=["exec", "file_transfer"],
        certificate="cert-data",
    )

    assert config.capabilities == ["exec", "file_transfer"]
    assert config.certificate == "cert-data"


def test_connector_config_schema_requires_host_and_version() -> None:
    with pytest.raises(ValidationError):
        ConnectorConfigSchema()
