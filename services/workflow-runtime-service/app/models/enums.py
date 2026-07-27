"""Enumerations for the workflow runtime service's persisted domain.

Per docs/042 "STATE MACHINE"/"REPLAY"/"ROLLBACK"/"COMPENSATION"/
"TIMERS"/"VARIABLES"/"REPORTING"/etc. Sections that enumerate concrete
values verbatim are copied exactly; sections that only name a
"Support"/"Collect"/"Generate" capability list (without a value
enumeration) are given a small, conventional value set documented as
derived in that enum's own docstring -- the same precedent
``services/automation-service``'s/``services/playbook-service``'s own
``app/models/enums.py`` established.

Every persisted status column here is this service's OWN enum, never a
bare re-export of ``shared_core.workflow``'s in-memory equivalents
(``WorkflowState``, ``ApprovalDecision``) -- those SDK enums are
purely in-process value objects with no database-column concerns of
their own, and (per direct comparison) docs/042's own verbatim state
list is not even the same set of values as ``WorkflowState``'s (it
swaps ``Pending`` for ``Queued`` and adds ``Checkpointed``). A
translation layer between this module's :class:`WorkflowInstanceStatus`
and the SDK's own :class:`~shared_core.workflow.WorkflowState` lives in
``app/services/instance.py``. ``shared_core.workflow.NodeType`` (the
SDK's own 20-member node-type vocabulary) IS reused directly, though --
it is genuinely shared vocabulary between the SDK's graph definitions
and this service's own persisted step/timer/compensation rows, not a
service-specific concept docs/042 redefines.
"""

from __future__ import annotations

from enum import StrEnum


class WorkflowInstanceStatus(StrEnum):
    """Per docs/042 "STATE MACHINE" (12 values, verbatim). Distinct from
    ``shared_core.workflow.WorkflowState``'s own 11-value set -- see
    this module's own docstring.
    """

    CREATED = "created"
    QUEUED = "queued"
    WAITING = "waiting"
    RUNNING = "running"
    PAUSED = "paused"
    CHECKPOINTED = "checkpointed"
    RETRYING = "retrying"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    ARCHIVED = "archived"


class NodeExecutionStatus(StrEnum):
    """Derived from docs/042 "DAG EXECUTION"/"STATE MACHINE" -- one
    node's own lifecycle within a running instance, the same
    conventional per-step status shape
    ``services/automation-service``'s own ``ExecutionStepStatus``
    established.
    """

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    SKIPPED = "skipped"


class CheckpointType(StrEnum):
    """Per docs/042 "CHECKPOINTING" "Support" (2 values, verbatim:
    Automatic Checkpoints, Manual Checkpoints).
    """

    AUTOMATIC = "automatic"
    MANUAL = "manual"


class ReplayType(StrEnum):
    """Derived from docs/042 "REPLAY" "Support" (Replay Workflow,
    Replay Failed Steps, Replay From Checkpoint name three distinct
    replay shapes; "Replay History"/"Execution Comparison"/"Replay
    Validation" describe behavior, not a type of their own).
    """

    FULL = "full"
    FAILED_STEPS = "failed_steps"
    FROM_CHECKPOINT = "from_checkpoint"


class RollbackType(StrEnum):
    """Per docs/042 "ROLLBACK" "Support" (4 values, verbatim: Workflow
    Rollback, Step Rollback, Automatic Rollback, Manual Rollback).
    """

    WORKFLOW = "workflow"
    STEP = "step"
    AUTOMATIC = "automatic"
    MANUAL = "manual"


class RollbackStatus(StrEnum):
    """Derived from docs/042 "ROLLBACK" ("Rollback Validation"/"Rollback
    Reports" describe behavior, not a status of their own), the same
    lifecycle shape every prior AI-IOS workflow-shaped table
    established.
    """

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class CompensationStatus(StrEnum):
    """Derived from docs/042 "COMPENSATION" "Support" ("Compensation
    Audit" implies recording each action's own outcome).
    """

    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class TimerType(StrEnum):
    """Per docs/042 "TIMERS" "Support" (6 of 7 values, verbatim: Delay,
    Wait, Cron, Timeout, Recurring Timers, Event Timeout; "Scheduled
    Resume" describes behavior -- resuming a paused instance when a
    timer fires -- not a timer type of its own).
    """

    DELAY = "delay"
    WAIT = "wait"
    CRON = "cron"
    TIMEOUT = "timeout"
    RECURRING = "recurring"
    EVENT_TIMEOUT = "event_timeout"


class WorkflowVariableScope(StrEnum):
    """Per docs/042 "VARIABLES" "Support" (7 values, verbatim). Distinct
    from ``shared_core.workflow.VariableScope``'s own 6-value set (which
    has no ``NODE`` scope and names ``SYSTEM``/``CONTEXT`` instead of
    ``GLOBAL``/``NODE``) -- see this module's own docstring.
    """

    GLOBAL = "global"
    WORKFLOW = "workflow"
    NODE = "node"
    ENVIRONMENT = "environment"
    SECRET = "secret"
    COMPUTED = "computed"
    RUNTIME = "runtime"


class ApprovalDecisionStatus(StrEnum):
    """Mirrors ``shared_core.workflow.ApprovalDecision``'s own 5 values
    exactly, as this service's own persisted-column enum -- see this
    module's own docstring for why a DB column never stores an SDK
    in-memory enum directly.
    """

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    ESCALATED = "escalated"
    EXPIRED = "expired"


class WorkflowReportType(StrEnum):
    """Per docs/042 "REPORTING" "Generate" (6 values, verbatim)."""

    EXECUTION = "execution"
    PERFORMANCE = "performance"
    FAILURE = "failure"
    APPROVAL = "approval"
    WORKFLOW_HISTORY = "workflow_history"
    EXECUTIVE_DASHBOARD = "executive_dashboard"


class WorkflowTriggerType(StrEnum):
    """Derived from docs/042 "WORKFLOW EXECUTION"/"TIMERS" ("Scheduled
    Resume", "Cron") plus "EVENT-DRIVEN EXECUTION" -- distinguishes how
    an instance came to exist, the same distinction
    ``services/automation-service``'s own schedule-fired-vs-interactive
    execution split already established (a schedule-fired instance has
    no interactive caller identity to resolve credentials with).
    """

    MANUAL = "manual"
    SCHEDULED = "scheduled"
    EVENT = "event"


class AuditOutcome(StrEnum):
    """Reused ``SUCCESS``/``FAILURE`` shape, the same convention every
    prior AI-IOS audit-trail table established.
    """

    SUCCESS = "success"
    FAILURE = "failure"


__all__ = [
    "ApprovalDecisionStatus",
    "AuditOutcome",
    "CheckpointType",
    "CompensationStatus",
    "NodeExecutionStatus",
    "ReplayType",
    "RollbackStatus",
    "RollbackType",
    "TimerType",
    "WorkflowInstanceStatus",
    "WorkflowReportType",
    "WorkflowTriggerType",
    "WorkflowVariableScope",
]
