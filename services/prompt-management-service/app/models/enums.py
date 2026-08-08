"""Every enum this service's own models and pure engines use.

Every ``Mapped[SomeEnum]`` column here is backed by ``String`` at the
database level, per this platform's own established "enum-as-str" rule:
a loaded row's own enum-typed attribute is a plain ``str`` at runtime
(there is no SQLAlchemy ``Enum`` column type in use anywhere in this
codebase), so comparisons use ``==`` against the enum class, never
``is``, and formatting uses ``str(value)``, never ``value.value``.
"""

from __future__ import annotations

from enum import StrEnum


class PromptType(StrEnum):
    """The fifteen prompt types docs/061's own "PROMPT TYPES" section names."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    DEVELOPER = "developer"
    AGENT = "agent"
    WORKFLOW = "workflow"
    AUTOMATION = "automation"
    VALIDATION = "validation"
    RAG = "rag"
    CLASSIFICATION = "classification"
    SUMMARIZATION = "summarization"
    EXTRACTION = "extraction"
    GENERATION = "generation"
    EVALUATION = "evaluation"
    CUSTOM = "custom"


class PromptCategory(StrEnum):
    """The fifteen categories docs/061's own "PROMPT CATEGORIES" names.

    A first-class ``prompt_categories`` table also exists, for
    organization-defined categories with their own descriptions and
    ownership. This enum is the *platform's* own fixed taxonomy, which
    that table's rows reference -- the two are not redundant: one is
    the closed vocabulary this service ships with, the other is the
    open set a tenant curates on top of it.
    """

    INFRASTRUCTURE = "infrastructure"
    AUTOMATION = "automation"
    WORKFLOW = "workflow"
    VALIDATION = "validation"
    MONITORING = "monitoring"
    KNOWLEDGE_GRAPH = "knowledge_graph"
    COMPLIANCE = "compliance"
    SECURITY = "security"
    INCIDENT_MANAGEMENT = "incident_management"
    CHANGE_MANAGEMENT = "change_management"
    REPORTING = "reporting"
    AI_ASSISTANT = "ai_assistant"
    AI_AGENT = "ai_agent"
    DEVELOPER = "developer"
    CUSTOM = "custom"


class PromptLifecycleStatus(StrEnum):
    """One prompt's own progression through docs/061's own "PROMPT
    LIFECYCLE" section.

    ``Rollback``, ``Clone``, and ``Fork`` from that list are
    *transitions*, not resting states -- a rollback lands a prompt back
    in ``PUBLISHED`` pointing at an earlier version, and a clone/fork
    produces a new prompt in ``DRAFT``. Modelling them as statuses
    would make "this prompt is currently a fork" a permanent, unusable
    state.
    """

    DRAFT = "draft"
    REVIEW = "review"
    APPROVAL = "approval"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class PromptVersionStatus(StrEnum):
    """One immutable prompt revision's own state.

    Distinct from :class:`PromptLifecycleStatus`, which describes the
    prompt *identity*: a published prompt always points at exactly one
    ``PUBLISHED`` version while older ones stay ``SUPERSEDED`` and
    remain readable, which is what makes rollback and version
    comparison real rather than nominal.
    """

    DRAFT = "draft"
    PUBLISHED = "published"
    SUPERSEDED = "superseded"
    ROLLED_BACK = "rolled_back"


class VersionBump(StrEnum):
    """Which semantic-version component a new revision advances."""

    MAJOR = "major"
    MINOR = "minor"
    PATCH = "patch"


class VariableKind(StrEnum):
    """The variable sources docs/061's own "VARIABLE MANAGEMENT" names.

    ``SECRET_REFERENCE`` never stores a value -- it stores a reference
    resolved live against secrets-management-service at render time, so
    a secret's plaintext has no path into this service's own database
    or into a rendered prompt that gets logged.
    """

    STATIC = "static"
    DYNAMIC = "dynamic"
    ENVIRONMENT = "environment"
    ORGANIZATION = "organization"
    PROJECT = "project"
    RUNTIME = "runtime"
    SECRET_REFERENCE = "secret_reference"
    COMPUTED = "computed"


class VariableType(StrEnum):
    """The declared type a variable's own value is validated against."""

    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"


class TemplateFormat(StrEnum):
    """How one template's body is written.

    Deliberately narrower than
    ``shared_core.notifications.templates.TemplateFormat`` (HTML /
    Markdown / plain text): a prompt is text sent to a model, so HTML
    is meaningless here, while structured formats a model is asked to
    fill are not.
    """

    PLAIN_TEXT = "plain_text"
    MARKDOWN = "markdown"
    JSON = "json"
    XML = "xml"


class ReviewDecision(StrEnum):
    """One reviewer's verdict on a prompt version."""

    PENDING = "pending"
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"
    REJECTED = "rejected"


class ApprovalStatus(StrEnum):
    """One approval gate's own state ("GOVERNANCE": Approval Workflow)."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    WITHDRAWN = "withdrawn"


class TestKind(StrEnum):
    """The eight test kinds docs/061's own "PROMPT TESTING" section names."""

    MANUAL = "manual"
    AUTOMATED = "automated"
    REGRESSION = "regression"
    GOLDEN_DATASET = "golden_dataset"
    EDGE_CASE = "edge_case"
    LOAD = "load"
    COMPARISON = "comparison"
    SNAPSHOT = "snapshot"


class TestRunStatus(StrEnum):
    """One test definition's own most recent run state."""

    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    ERRORED = "errored"


class EvaluationMetric(StrEnum):
    """The nine metrics docs/061's own "PROMPT EVALUATION" section names."""

    RESPONSE_ACCURACY = "response_accuracy"
    COMPLETENESS = "completeness"
    CONSISTENCY = "consistency"
    LATENCY = "latency"
    TOKEN_USAGE = "token_usage"
    COST = "cost"
    HALLUCINATION = "hallucination"
    SAFETY = "safety"
    CUSTOM = "custom"


class AbTestStatus(StrEnum):
    """One A/B experiment's own state ("A/B TESTING")."""

    DRAFT = "draft"
    RUNNING = "running"
    COMPLETED = "completed"
    PROMOTED = "promoted"
    ROLLED_BACK = "rolled_back"
    CANCELLED = "cancelled"


class AbTestArm(StrEnum):
    """Which side of an experiment one execution was routed to."""

    CONTROL = "control"
    VARIANT = "variant"


class ExecutionStatus(StrEnum):
    """One recorded prompt execution's own outcome."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"


class SecurityFinding(StrEnum):
    """What a security scan detected (docs/061's own "SECURITY" section).

    ``SECRET_DETECTED``/``PII_DETECTED`` come from the same redaction
    pattern set every AI-IOS guardrail module uses; the rest are
    prompt-specific and have no precedent elsewhere in the platform.
    """

    SECRET_DETECTED = "secret_detected"
    PII_DETECTED = "pii_detected"
    PROMPT_INJECTION = "prompt_injection"
    UNSAFE_INSTRUCTION = "unsafe_instruction"
    RESTRICTED_KEYWORD = "restricted_keyword"
    TEMPLATE_SYNTAX_ERROR = "template_syntax_error"
    UNDECLARED_VARIABLE = "undeclared_variable"


class SecuritySeverity(StrEnum):
    """How badly one scan finding should block publication."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ScanStatus(StrEnum):
    """One security scan's own verdict.

    ``BLOCKED`` is a first-class outcome rather than folded into
    ``FAILED``: a scan that ran perfectly and found a critical problem
    is not the same event as a scan that could not run, and only the
    former should stop a publish.
    """

    CLEAN = "clean"
    FLAGGED = "flagged"
    BLOCKED = "blocked"


class OptimizationKind(StrEnum):
    """The eight optimization strategies docs/061's own "PROMPT
    OPTIMIZATION" section names."""

    TOKEN = "token"
    COST = "cost"
    LATENCY = "latency"
    COMPRESSION = "compression"
    INSTRUCTION_REFINEMENT = "instruction_refinement"
    FEW_SHOT = "few_shot"
    CHAIN = "chain"
    AUTOMATIC_SUGGESTION = "automatic_suggestion"


class OptimizationStatus(StrEnum):
    """Whether an optimization suggestion has been acted on.

    A suggestion is never applied automatically -- a prompt's exact
    wording is the thing under version control and approval here, so
    rewriting it without a human accepting the change would bypass the
    entire governance workflow this service exists to enforce.
    """

    SUGGESTED = "suggested"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class SharingScope(StrEnum):
    """Who can read one prompt ("SHARING")."""

    PRIVATE = "private"
    PROJECT = "project"
    ORGANIZATION = "organization"
    SHARED = "shared"


class ReportKind(StrEnum):
    """The seven report kinds docs/061's own "REPORTING" section names."""

    USAGE = "usage"
    OPTIMIZATION = "optimization"
    COST = "cost"
    EVALUATION = "evaluation"
    SECURITY = "security"
    APPROVAL = "approval"
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
    """What an audit row records (docs/061's own "AUDIT" section)."""

    PROMPT_CREATED = "prompt_created"
    PROMPT_UPDATED = "prompt_updated"
    VERSION_CREATED = "version_created"
    REVIEW_SUBMITTED = "review_submitted"
    APPROVAL_DECIDED = "approval_decided"
    PUBLISHED = "published"
    ROLLED_BACK = "rolled_back"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"
    CLONED = "cloned"
    TESTED = "tested"
    EVALUATED = "evaluated"
    OPTIMIZED = "optimized"
    SECURITY_SCANNED = "security_scanned"
    AB_TEST_DECIDED = "ab_test_decided"
    ADMINISTRATIVE = "administrative"


__all__ = [
    "AbTestArm",
    "AbTestStatus",
    "ApprovalStatus",
    "AuditAction",
    "EvaluationMetric",
    "ExecutionStatus",
    "OptimizationKind",
    "OptimizationStatus",
    "PromptCategory",
    "PromptLifecycleStatus",
    "PromptType",
    "PromptVersionStatus",
    "ReportFormat",
    "ReportKind",
    "ReportStatus",
    "ReviewDecision",
    "ScanStatus",
    "SecurityFinding",
    "SecuritySeverity",
    "SharingScope",
    "TemplateFormat",
    "TestKind",
    "TestRunStatus",
    "VariableKind",
    "VariableType",
    "VersionBump",
]
