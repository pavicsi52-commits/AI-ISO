"""Enumerations for the AI Assistant Service, per docs/046.

**Reuse note**: ``shared_core.exceptions.ai.AIError`` (AIIOS-AI-0001)
already exists platform-wide and is raised directly by this service's
own model/embedding/tool failures rather than defining a parallel
exception. ``shared_core.plugins.ai.AiExtensions`` is the registered
extension point through which a plugin contributes a custom model,
prompt, agent, or embedding provider -- its own docstring is explicit
that it tracks *what* a plugin contributed and leaves running
inference to the host service, which is this one.
"""

from __future__ import annotations

from enum import StrEnum


class AgentType(StrEnum):
    """Per docs/046 "AGENT TYPES"."""

    PLANNER = "planner"
    REASONING = "reasoning"
    INFRASTRUCTURE = "infrastructure"
    AUTOMATION = "automation"
    VALIDATION = "validation"
    MONITORING = "monitoring"
    CONFIGURATION = "configuration"
    KNOWLEDGE = "knowledge"
    WORKFLOW = "workflow"
    REPORTING = "reporting"
    SECURITY = "security"
    CUSTOM = "custom"


class ModelProvider(StrEnum):
    """Per docs/046 "MODEL MANAGEMENT".

    ``LOCAL`` covers "Local Models" -- an OpenAI-compatible endpoint
    hosted anywhere, distinct from ``OLLAMA``/``VLLM`` which have their
    own documented protocols.
    """

    OPENAI = "openai"
    AZURE_OPENAI = "azure_openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    OLLAMA = "ollama"
    VLLM = "vllm"
    OPENROUTER = "openrouter"
    LOCAL = "local"


class MessageRole(StrEnum):
    """Who authored a conversation message.

    Not its own named list in docs/046, but required by every chat
    protocol this service speaks; ``TOOL`` carries a tool result back
    into the model's own context.
    """

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ConversationStatus(StrEnum):
    """A conversation's own lifecycle state."""

    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"


class ToolCallStatus(StrEnum):
    """One tool invocation's own outcome."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DENIED = "denied"


class ToolKind(StrEnum):
    """Per docs/046 "TOOL CALLING" -- what a registered tool actually does."""

    INVENTORY_QUERY = "inventory_query"
    AUTOMATION_EXECUTION = "automation_execution"
    WORKFLOW_EXECUTION = "workflow_execution"
    VALIDATION_EXECUTION = "validation_execution"
    MONITORING_QUERY = "monitoring_query"
    ALERT_QUERY = "alert_query"
    CONFIGURATION_QUERY = "configuration_query"
    REPORTING = "reporting"
    SEARCH = "search"
    REST_API = "rest_api"
    PLUGIN = "plugin"
    CUSTOM = "custom"


class DocumentSourceType(StrEnum):
    """Per docs/046 "KNOWLEDGE SOURCES"."""

    INVENTORY = "inventory"
    DISCOVERY = "discovery"
    CONFIGURATION_MANAGEMENT = "configuration_management"
    AUTOMATION = "automation"
    WORKFLOW_RUNTIME = "workflow_runtime"
    VALIDATION = "validation"
    MONITORING = "monitoring"
    ALERTING = "alerting"
    REPORTS = "reports"
    DOCUMENTATION = "documentation"
    POLICIES = "policies"
    PLAYBOOKS = "playbooks"
    RUNBOOKS = "runbooks"
    WIKI = "wiki"
    UPLOADED = "uploaded"


class MemoryScope(StrEnum):
    """Per docs/046 "MEMORY" -- how long a remembered fact survives and
    who it applies to.
    """

    CONVERSATION = "conversation"
    SESSION = "session"
    USER = "user"
    ORGANIZATION = "organization"
    PROJECT = "project"


class RetrievalStrategy(StrEnum):
    """Per docs/046 "RAG" -- how candidate chunks were found."""

    VECTOR = "vector"
    KEYWORD = "keyword"
    HYBRID = "hybrid"


class RecommendationType(StrEnum):
    """What a generated recommendation is about, spanning docs/046's own
    AUTOMATION/VALIDATION/MONITORING/CONFIGURATION assistance sections.
    """

    PLAYBOOK = "playbook"
    WORKFLOW = "workflow"
    AUTOMATION = "automation"
    REMEDIATION = "remediation"
    ROOT_CAUSE = "root_cause"
    CAPACITY = "capacity"
    CONFIGURATION = "configuration"
    RISK = "risk"


class RecommendationStatus(StrEnum):
    """A recommendation's own review state."""

    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    APPLIED = "applied"


class PromptStatus(StrEnum):
    """Per docs/046 "PROMPT MANAGEMENT": Versioning, Approval, Rollback."""

    DRAFT = "draft"
    APPROVED = "approved"
    ARCHIVED = "archived"


class AiReportType(StrEnum):
    """Per docs/046 "REPORT GENERATION"."""

    EXECUTIVE = "executive"
    OPERATIONAL = "operational"
    INCIDENT_SUMMARY = "incident_summary"
    HEALTH_SUMMARY = "health_summary"
    CAPACITY = "capacity"
    AUTOMATION = "automation"
    VALIDATION = "validation"
    COMPLIANCE = "compliance"
    NATURAL_LANGUAGE = "natural_language"


class GuardrailVerdict(StrEnum):
    """Per docs/046 "SAFETY" -- what a guardrail decided about content."""

    ALLOWED = "allowed"
    REDACTED = "redacted"
    BLOCKED = "blocked"


class FeedbackRating(StrEnum):
    """Per docs/046 "ANALYTICS": Feedback Scores."""

    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


class AuditOutcome(StrEnum):
    """Matches every prior AI-IOS service's own identical shape."""

    SUCCESS = "success"
    FAILURE = "failure"


__all__ = [
    "AgentType",
    "AiReportType",
    "AuditOutcome",
    "ConversationStatus",
    "DocumentSourceType",
    "FeedbackRating",
    "GuardrailVerdict",
    "MemoryScope",
    "MessageRole",
    "ModelProvider",
    "PromptStatus",
    "RecommendationStatus",
    "RecommendationType",
    "RetrievalStrategy",
    "ToolCallStatus",
    "ToolKind",
]
