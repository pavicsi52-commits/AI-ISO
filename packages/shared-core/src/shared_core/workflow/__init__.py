"""Enterprise Workflow SDK.

Per docs/028_Enterprise_Workflow_SDK.md.txt. A DAG-based workflow
engine: definitions (YAML/JSON/Python DSL), validation, compilation,
a state machine, checkpointing, rollback/compensation (Saga pattern),
human approval, conditional/parallel/loop-capable execution, retry and
circuit breaking, and integration with this codebase's event, queue,
scheduler, telemetry, metrics, and audit frameworks (Prompts 020, 021,
024, 026).

Business-specific node types (``TASK``, ``CONNECTOR``, ``PLUGIN``,
``AI``, ``WEBHOOK``, ``QUEUE``, ``EVENT``, ``HUMAN_TASK``,
``APPROVAL``, ``LOOP``, ``SUB_WORKFLOW``) are never implemented by this
SDK itself, per docs/028 "DO NOT IMPLEMENT" -- a caller registers
whatever handlers it needs into a
:class:`~shared_core.workflow.executor.NodeHandlerRegistry` (directly,
or via ``@node_handler(node_type)``) and this SDK handles graph
execution, state, retry, rollback, and observability identically
regardless of what those handlers actually do.
"""

from __future__ import annotations

from shared_core.workflow.approval import ApprovalDecision, ApprovalRequest
from shared_core.workflow.audit import (
    audit_approval_decision,
    audit_execution_completed,
    audit_execution_failed,
    audit_execution_started,
    audit_privileged_access,
    audit_rollback_executed,
    audit_workflow_created,
    audit_workflow_deleted,
    audit_workflow_updated,
)
from shared_core.workflow.checkpoint import Checkpoint, CheckpointStore
from shared_core.workflow.compensation import CompensationAction, CompensationRegistry
from shared_core.workflow.compiler import CompiledWorkflow, compile_workflow
from shared_core.workflow.conditions import (
    Rule,
    evaluate_if_else,
    evaluate_match,
    evaluate_rules,
    evaluate_switch,
)
from shared_core.workflow.constants import (
    DEFAULT_APPROVAL_TIMEOUT_SECONDS,
    DEFAULT_CHECKPOINT_INTERVAL_SECONDS,
    DEFAULT_CIRCUIT_BREAKER_FAILURE_THRESHOLD,
    DEFAULT_CIRCUIT_BREAKER_RECOVERY_SECONDS,
    DEFAULT_LOOP_MAX_ITERATIONS,
    DEFAULT_MAX_DAG_NODES,
    DEFAULT_MAX_PARALLEL_BRANCHES,
    DEFAULT_RETRY_MAX_ATTEMPTS,
    DEFAULT_SOURCE_SERVICE,
    DEFAULT_TASK_TIMEOUT_SECONDS,
    DEFAULT_WORKFLOW_TIMEOUT_SECONDS,
)
from shared_core.workflow.context import WorkflowContext, new_execution_id
from shared_core.workflow.dag import detect_cycle, execution_plan, topological_order, validate_dag
from shared_core.workflow.decorators import get_node_type, node_handler, retryable, timed
from shared_core.workflow.definition import WorkflowDefinition
from shared_core.workflow.edges import EdgeDefinition
from shared_core.workflow.engine import EventHandler, WorkflowEngine
from shared_core.workflow.events import (
    TaskCompletedEvent,
    TaskFailedEvent,
    TaskStartedEvent,
    WorkflowCancelledEvent,
    WorkflowCompletedEvent,
    WorkflowEvent,
    WorkflowFailedEvent,
    WorkflowRolledBackEvent,
    WorkflowStartedEvent,
    build_workflow_event,
)
from shared_core.workflow.exceptions import (
    ApprovalRejectedError,
    ApprovalTimeoutError,
    CheckpointError,
    CompensationError,
    CycleDetectedError,
    ExpressionEvaluationError,
    InvalidStateTransitionError,
    InvalidWorkflowDefinitionError,
    MaxIterationsExceededError,
    NodeNotFoundError,
    RollbackError,
    TaskExecutionError,
    WorkflowNotFoundError,
    WorkflowTimeoutError,
)
from shared_core.workflow.execution import NodeExecutionResult, WorkflowExecution
from shared_core.workflow.executor import NodeExecutor, NodeHandler, NodeHandlerRegistry
from shared_core.workflow.expressions import evaluate_condition, evaluate_expression
from shared_core.workflow.factory import create_workflow_framework
from shared_core.workflow.graph import WorkflowGraph
from shared_core.workflow.health import WorkflowHealthReport, build_health_report
from shared_core.workflow.helpers import (
    execution_summary,
    format_duration,
    node_result_summary,
    workflow_summary,
)
from shared_core.workflow.manager import WorkflowManager
from shared_core.workflow.metrics import (
    measure_task,
    record_approval_time,
    record_execution_started,
    record_failure,
    record_queue_time,
    record_retry,
    record_rollback,
    record_success,
    record_task_duration,
    workflow_approval_seconds,
    workflow_execution_seconds,
    workflow_executions_total,
    workflow_failure_total,
    workflow_queue_seconds,
    workflow_retries_total,
    workflow_rollbacks_total,
    workflow_success_total,
    workflow_task_duration_seconds,
)
from shared_core.workflow.middleware import (
    Handler,
    Middleware,
    PermissionChecker,
    WorkflowOperationContext,
    apply_middleware,
    audit_privileged_middleware,
    build_rbac_middleware,
    build_tenant_isolation_middleware,
    logging_middleware,
)
from shared_core.workflow.nodes import NodeDefinition, NodeType
from shared_core.workflow.parallel import BranchResult, run_parallel
from shared_core.workflow.parser import WorkflowBuilder, parse_dict, parse_json, parse_yaml
from shared_core.workflow.queue import (
    DEFAULT_WORKFLOW_TASK_QUEUE_NAME,
    WorkflowTaskHandler,
    WorkflowTaskQueue,
    build_task_message,
)
from shared_core.workflow.registry import WorkflowRegistry
from shared_core.workflow.retry import CircuitBreaker, CircuitState, workflow_retry_policy
from shared_core.workflow.rollback import rollback_workflow
from shared_core.workflow.runtime import WorkflowRuntime
from shared_core.workflow.scheduler import (
    WorkflowTrigger,
    build_scheduled_workflow_job,
    cron_schedule,
    delayed_schedule,
    recurring_schedule,
)
from shared_core.workflow.state_machine import StateMachine, WorkflowState
from shared_core.workflow.telemetry import (
    trace_ai_request,
    trace_connector_execution,
    trace_workflow_execution,
    trace_workflow_step,
)
from shared_core.workflow.template import WorkflowTemplate
from shared_core.workflow.timeout import with_timeout
from shared_core.workflow.validator import build_graph, validate_definition
from shared_core.workflow.variables import Variable, VariableScope, VariableStore

__all__ = [
    "DEFAULT_APPROVAL_TIMEOUT_SECONDS",
    "DEFAULT_CHECKPOINT_INTERVAL_SECONDS",
    "DEFAULT_CIRCUIT_BREAKER_FAILURE_THRESHOLD",
    "DEFAULT_CIRCUIT_BREAKER_RECOVERY_SECONDS",
    "DEFAULT_LOOP_MAX_ITERATIONS",
    "DEFAULT_MAX_DAG_NODES",
    "DEFAULT_MAX_PARALLEL_BRANCHES",
    "DEFAULT_RETRY_MAX_ATTEMPTS",
    "DEFAULT_SOURCE_SERVICE",
    "DEFAULT_TASK_TIMEOUT_SECONDS",
    "DEFAULT_WORKFLOW_TASK_QUEUE_NAME",
    "DEFAULT_WORKFLOW_TIMEOUT_SECONDS",
    "ApprovalDecision",
    "ApprovalRejectedError",
    "ApprovalRequest",
    "ApprovalTimeoutError",
    "BranchResult",
    "Checkpoint",
    "CheckpointError",
    "CheckpointStore",
    "CircuitBreaker",
    "CircuitState",
    "CompensationAction",
    "CompensationError",
    "CompensationRegistry",
    "CompiledWorkflow",
    "CycleDetectedError",
    "EdgeDefinition",
    "EventHandler",
    "ExpressionEvaluationError",
    "Handler",
    "InvalidStateTransitionError",
    "InvalidWorkflowDefinitionError",
    "MaxIterationsExceededError",
    "Middleware",
    "NodeDefinition",
    "NodeExecutionResult",
    "NodeExecutor",
    "NodeHandler",
    "NodeHandlerRegistry",
    "NodeNotFoundError",
    "NodeType",
    "PermissionChecker",
    "RollbackError",
    "Rule",
    "StateMachine",
    "TaskCompletedEvent",
    "TaskExecutionError",
    "TaskFailedEvent",
    "TaskStartedEvent",
    "Variable",
    "VariableScope",
    "VariableStore",
    "WorkflowBuilder",
    "WorkflowCancelledEvent",
    "WorkflowCompletedEvent",
    "WorkflowContext",
    "WorkflowDefinition",
    "WorkflowEngine",
    "WorkflowEvent",
    "WorkflowExecution",
    "WorkflowFailedEvent",
    "WorkflowGraph",
    "WorkflowHealthReport",
    "WorkflowManager",
    "WorkflowNotFoundError",
    "WorkflowOperationContext",
    "WorkflowRegistry",
    "WorkflowRolledBackEvent",
    "WorkflowRuntime",
    "WorkflowStartedEvent",
    "WorkflowState",
    "WorkflowTaskHandler",
    "WorkflowTaskQueue",
    "WorkflowTemplate",
    "WorkflowTimeoutError",
    "WorkflowTrigger",
    "apply_middleware",
    "audit_approval_decision",
    "audit_execution_completed",
    "audit_execution_failed",
    "audit_execution_started",
    "audit_privileged_access",
    "audit_privileged_middleware",
    "audit_rollback_executed",
    "audit_workflow_created",
    "audit_workflow_deleted",
    "audit_workflow_updated",
    "build_graph",
    "build_health_report",
    "build_rbac_middleware",
    "build_scheduled_workflow_job",
    "build_task_message",
    "build_tenant_isolation_middleware",
    "build_workflow_event",
    "compile_workflow",
    "create_workflow_framework",
    "cron_schedule",
    "delayed_schedule",
    "detect_cycle",
    "evaluate_condition",
    "evaluate_expression",
    "evaluate_if_else",
    "evaluate_match",
    "evaluate_rules",
    "evaluate_switch",
    "execution_plan",
    "execution_summary",
    "format_duration",
    "get_node_type",
    "logging_middleware",
    "measure_task",
    "new_execution_id",
    "node_handler",
    "node_result_summary",
    "parse_dict",
    "parse_json",
    "parse_yaml",
    "record_approval_time",
    "record_execution_started",
    "record_failure",
    "record_queue_time",
    "record_retry",
    "record_rollback",
    "record_success",
    "record_task_duration",
    "recurring_schedule",
    "retryable",
    "rollback_workflow",
    "run_parallel",
    "timed",
    "topological_order",
    "trace_ai_request",
    "trace_connector_execution",
    "trace_workflow_execution",
    "trace_workflow_step",
    "validate_dag",
    "validate_definition",
    "with_timeout",
    "workflow_approval_seconds",
    "workflow_execution_seconds",
    "workflow_executions_total",
    "workflow_failure_total",
    "workflow_queue_seconds",
    "workflow_retries_total",
    "workflow_retry_policy",
    "workflow_rollbacks_total",
    "workflow_success_total",
    "workflow_summary",
    "workflow_task_duration_seconds",
]
