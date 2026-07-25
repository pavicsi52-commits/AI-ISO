"""Playbook/workflow execution status enumeration."""

from enum import StrEnum


class ExecutionStatus(StrEnum):
    """Lifecycle states for a playbook or workflow execution."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ROLLED_BACK = "rolled_back"
