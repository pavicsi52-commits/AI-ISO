"""Every enum this service's own models and pure engines use.

Every ``Mapped[SomeEnum]`` column here is backed by ``String`` at the
database level -- callers pass the column itself to a normaliser, never
the record, per this platform's own established "enum-as-str" rule: a
loaded row's own enum-typed attribute is a plain ``str`` at runtime
(there is no SQLAlchemy ``Enum`` column type in use anywhere in this
codebase), so comparisons and formatting use ``str(value)``, never
``value.value``.

``HealthStatus`` is reused directly from ``shared_core.enums
.health_status`` rather than redeclared here -- this platform's own
established health vocabulary, re-exported from :mod:`app.models` for a
single import surface.
"""

from __future__ import annotations

from enum import StrEnum


class AgentType(StrEnum):
    """The fourteen agent types docs/060's own "AGENT TYPES" section names."""

    PLANNER = "planner"
    EXECUTOR = "executor"
    RESEARCHER = "researcher"
    REVIEWER = "reviewer"
    VALIDATOR = "validator"
    COORDINATOR = "coordinator"
    MONITORING = "monitoring"
    AUTOMATION = "automation"
    INFRASTRUCTURE = "infrastructure"
    COMPLIANCE = "compliance"
    SECURITY = "security"
    KNOWLEDGE_GRAPH = "knowledge_graph"
    REPORTING = "reporting"
    CUSTOM = "custom"


class AgentLifecycleStatus(StrEnum):
    """One agent definition's own progression through docs/060's own
    "AGENT LIFECYCLE" section -- Registration/Initialization/
    Configuration/Activation/Execution/Pause/Resume/Disable/Upgrade/
    Retirement mapped onto a real state machine. "Execution" and
    "Resume" are transitions (tracked via ``agent_executions`` and the
    ``activate`` action respectively), not persistent states of their
    own.
    """

    REGISTERED = "registered"
    INITIALIZING = "initializing"
    CONFIGURED = "configured"
    ACTIVE = "active"
    PAUSED = "paused"
    DISABLED = "disabled"
    UPGRADING = "upgrading"
    RETIRED = "retired"


class MemoryScope(StrEnum):
    """The scopes docs/060's own "MEMORY" section names, most-specific-first."""

    TASK = "task"
    CONVERSATION = "conversation"
    SESSION = "session"
    SHORT_TERM = "short_term"
    LONG_TERM = "long_term"
    KNOWLEDGE_REFERENCE = "knowledge_reference"


class SessionStatus(StrEnum):
    """One agent session's own state."""

    ACTIVE = "active"
    IDLE = "idle"
    EXPIRED = "expired"
    CLOSED = "closed"


class TaskStatus(StrEnum):
    """One agent task's own progression through docs/060's own "TASK
    MANAGEMENT" section.
    """

    PENDING = "pending"
    QUEUED = "queued"
    ASSIGNED = "assigned"
    RUNNING = "running"
    RETRYING = "retrying"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class TaskPriority(StrEnum):
    """The five priority levels ``shared_core.queue.priority`` already
    establishes (RabbitMQ ``x-max-priority``), reused here as this
    table's own literal column values.
    """

    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"
    BACKGROUND = "background"


class WorkflowRunStatus(StrEnum):
    """One LangGraph-style agent workflow run's own state."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED_FOR_APPROVAL = "paused_for_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class OrchestrationPattern(StrEnum):
    """The nine patterns docs/060's own "MULTI-AGENT ORCHESTRATION"
    section names -- which coordination strategy executed one
    workflow run.
    """

    HIERARCHICAL = "hierarchical"
    PEER_TO_PEER = "peer_to_peer"
    SUPERVISOR = "supervisor"
    PLANNER_EXECUTOR = "planner_executor"
    DELEGATION = "delegation"
    DYNAMIC_SELECTION = "dynamic_selection"
    TASK_DECOMPOSITION = "task_decomposition"
    RESULT_AGGREGATION = "result_aggregation"
    CONFLICT_RESOLUTION = "conflict_resolution"


class ToolKind(StrEnum):
    """The ten tool kinds docs/060's own "TOOL EXECUTION" section names."""

    REST = "rest"
    PYTHON = "python"
    SHELL = "shell"
    WORKFLOW = "workflow"
    AUTOMATION = "automation"
    KNOWLEDGE_GRAPH_QUERY = "knowledge_graph_query"
    DATABASE_QUERY = "database_query"
    CONNECTOR_SDK = "connector_sdk"
    WEBHOOK = "webhook"
    CUSTOM = "custom"


class PermissionCategory(StrEnum):
    """The capability categories an agent's own tool/delegation/memory/
    model access can be scoped by.

    Distinct from ``shared_core.plugins.permissions.PluginPermission``
    and from ``services/plugin-marketplace-service``'s own
    ``PluginPermissionCategory`` -- this service's own capability-grant
    model needs its own agent-shaped taxonomy (tool invocation,
    delegation to another agent, model access, ...), not a plugin's.
    """

    TOOL_INVOCATION = "tool_invocation"
    DATA_ACCESS = "data_access"
    NETWORK = "network"
    FILESYSTEM = "filesystem"
    MODEL_ACCESS = "model_access"
    DELEGATION = "delegation"
    MEMORY_ACCESS = "memory_access"
    ADMINISTRATIVE = "administrative"


class PermissionGrantStatus(StrEnum):
    """One requested capability's own grant state."""

    PENDING = "pending"
    GRANTED = "granted"
    DENIED = "denied"
    REVOKED = "revoked"


class GuardrailType(StrEnum):
    """The eight guardrail kinds docs/060's own "GUARDRAILS" section names."""

    PROMPT_VALIDATION = "prompt_validation"
    OUTPUT_VALIDATION = "output_validation"
    POLICY_ENFORCEMENT = "policy_enforcement"
    PII_DETECTION = "pii_detection"
    SECRET_REDACTION = "secret_redaction"
    RISK_CLASSIFICATION = "risk_classification"
    UNSAFE_ACTION_PREVENTION = "unsafe_action_prevention"
    EXECUTION_CONSTRAINT = "execution_constraint"


class ExecutionStatus(StrEnum):
    """One agent execution's own run state."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class ReasoningMode(StrEnum):
    """The eight reasoning modes docs/060's own "REASONING" section names."""

    CHAIN_OF_THOUGHT = "chain_of_thought"
    TREE_OF_THOUGHT = "tree_of_thought"
    PLAN_AND_EXECUTE = "plan_and_execute"
    REFLECTION = "reflection"
    SELF_VERIFICATION = "self_verification"
    TOOL_BASED = "tool_based"
    KNOWLEDGE_GRAPH = "knowledge_graph"
    HYBRID = "hybrid"


class ModelProvider(StrEnum):
    """The model providers docs/060's own "MODEL ROUTING" section names."""

    OPENAI = "openai"
    AZURE_OPENAI = "azure_openai"
    ANTHROPIC = "anthropic"
    GOOGLE_GEMINI = "google_gemini"
    OLLAMA = "ollama"
    VLLM = "vllm"
    OPENROUTER = "openrouter"
    LOCAL = "local"


class RoutingStrategy(StrEnum):
    """The four routing strategies docs/060's own "MODEL ROUTING" section names."""

    RULE_BASED = "rule_based"
    COST_AWARE = "cost_aware"
    LATENCY_AWARE = "latency_aware"
    FALLBACK = "fallback"


class BenchmarkStatus(StrEnum):
    """One benchmark suite run's own state."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentMarketplaceListingStatus(StrEnum):
    """One marketplace listing's own publication state."""

    DRAFT = "draft"
    PUBLISHED = "published"
    FEATURED = "featured"
    DEPRECATED = "deprecated"
    REMOVED = "removed"


class ReportKind(StrEnum):
    """The seven report kinds docs/060's own "REPORTING" section names."""

    EXECUTION = "execution"
    EVALUATION = "evaluation"
    BENCHMARK = "benchmark"
    COST = "cost"
    PERFORMANCE = "performance"
    USAGE = "usage"
    AUDIT = "audit"


class ReportFormat(StrEnum):
    """How a report is rendered."""

    JSON = "json"
    CSV = "csv"
    MARKDOWN = "markdown"


class ReportStatus(StrEnum):
    """A generated report's own build lifecycle."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AuditAction(StrEnum):
    """What an audit row records (docs/060's own "AUDIT" section)."""

    AGENT_REGISTERED = "agent_registered"
    AGENT_ACTIVATED = "agent_activated"
    AGENT_PAUSED = "agent_paused"
    AGENT_DISABLED = "agent_disabled"
    AGENT_RETIRED = "agent_retired"
    CONFIGURATION_CHANGED = "configuration_changed"
    EXECUTED = "executed"
    TOOL_USED = "tool_used"
    APPROVAL_DECIDED = "approval_decided"
    PERMISSION_GRANTED = "permission_granted"
    PERMISSION_REVOKED = "permission_revoked"
    MARKETPLACE_ACTION = "marketplace_action"
    ADMINISTRATIVE = "administrative"


__all__ = [
    "AgentLifecycleStatus",
    "AgentMarketplaceListingStatus",
    "AgentType",
    "AuditAction",
    "BenchmarkStatus",
    "ExecutionStatus",
    "GuardrailType",
    "MemoryScope",
    "ModelProvider",
    "OrchestrationPattern",
    "PermissionCategory",
    "PermissionGrantStatus",
    "ReasoningMode",
    "ReportFormat",
    "ReportKind",
    "ReportStatus",
    "RoutingStrategy",
    "SessionStatus",
    "TaskPriority",
    "TaskStatus",
    "ToolKind",
    "WorkflowRunStatus",
]
