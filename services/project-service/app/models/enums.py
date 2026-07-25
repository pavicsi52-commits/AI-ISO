"""Enumerations for the project service's persisted domain.

Per docs/034 "PROJECT STATUS"/"PROJECT VISIBILITY"/etc.
"""

from __future__ import annotations

from enum import StrEnum


class ProjectStatus(StrEnum):
    """Per docs/034 "PROJECT STATUS" (8 values, verbatim)."""

    DRAFT = "draft"
    PLANNING = "planning"
    ACTIVE = "active"
    MAINTENANCE = "maintenance"
    ARCHIVED = "archived"
    SUSPENDED = "suspended"
    COMPLETED = "completed"
    DELETED = "deleted"


class ProjectVisibility(StrEnum):
    """Per docs/034 "PROJECT VISIBILITY" (4 values, verbatim, including the
    explicitly-marked-optional "Public")."""

    PRIVATE = "private"
    INTERNAL = "internal"
    ORGANIZATION = "organization"
    PUBLIC = "public"


class ProjectPriority(StrEnum):
    """Docs/034's "PROJECT MODEL" names "Priority" as a field but never
    enumerates its values -- the standard four-tier enterprise scale.
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ProjectMemberStatus(StrEnum):
    """Backs "Deactivate Member"/"Reactivate Member" per docs/034 "PROJECT MEMBERS"."""

    ACTIVE = "active"
    SUSPENDED = "suspended"
    INACTIVE = "inactive"


class ProjectTemplateCategory(StrEnum):
    """Per docs/034 "PROJECT TEMPLATES" (7 values, verbatim)."""

    INFRASTRUCTURE = "infrastructure"
    AUTOMATION = "automation"
    VALIDATION = "validation"
    INDUSTRIAL = "industrial"
    CLOUD = "cloud"
    HYBRID = "hybrid"
    CUSTOM = "custom"


class ProjectResourceType(StrEnum):
    """Per docs/034 "PROJECT RESOURCES" (16 values, verbatim)."""

    INVENTORY_ASSET = "inventory_asset"
    DISCOVERED_ASSET = "discovered_asset"
    CONNECTOR = "connector"
    CREDENTIAL = "credential"
    SECRET = "secret"
    AUTOMATION_JOB = "automation_job"
    WORKFLOW_DEFINITION = "workflow_definition"
    WORKFLOW_EXECUTION = "workflow_execution"
    VALIDATION_PROFILE = "validation_profile"
    MONITORING_PROFILE = "monitoring_profile"
    DASHBOARD = "dashboard"
    REPORT = "report"
    AI_AGENT = "ai_agent"
    KNOWLEDGE_BASE = "knowledge_base"
    STORAGE_OBJECT = "storage_object"
    PLUGIN = "plugin"


class ProjectActivityType(StrEnum):
    """Per docs/034 "EVENTS"/"AUDIT": the narrative operations this service tracks."""

    PROJECT_CREATED = "project_created"
    PROJECT_UPDATED = "project_updated"
    PROJECT_ARCHIVED = "project_archived"
    PROJECT_RESTORED = "project_restored"
    PROJECT_DELETED = "project_deleted"
    PROJECT_CLONED = "project_cloned"
    MEMBER_ADDED = "member_added"
    MEMBER_REMOVED = "member_removed"
    ROLE_CHANGED = "role_changed"
    OWNERSHIP_TRANSFERRED = "ownership_transferred"
    SETTINGS_UPDATED = "settings_updated"
    TEMPLATE_USED = "template_used"
    RESOURCE_LINKED = "resource_linked"
    RESOURCE_UNLINKED = "resource_unlinked"
    IMPORTED = "imported"
    EXPORTED = "exported"


class AuditOutcome(StrEnum):
    """Whether an audited administrative action succeeded or failed."""

    SUCCESS = "success"
    FAILURE = "failure"


class ImportFormat(StrEnum):
    """Per docs/034 "IMPORT" (JSON/YAML/CSV/ZIP Package)."""

    JSON = "json"
    YAML = "yaml"
    CSV = "csv"
    ZIP = "zip"


class ExportFormat(StrEnum):
    """Per docs/034 "EXPORT" (JSON/YAML/ZIP Package/PDF Summary)."""

    JSON = "json"
    YAML = "yaml"
    ZIP = "zip"
    PDF = "pdf"


class ImportExportStatus(StrEnum):
    """Lifecycle of a background import/export job, per docs/034
    "EXPORT": "Background Processing"."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


__all__ = [
    "AuditOutcome",
    "ExportFormat",
    "ImportExportStatus",
    "ImportFormat",
    "ProjectActivityType",
    "ProjectMemberStatus",
    "ProjectPriority",
    "ProjectResourceType",
    "ProjectStatus",
    "ProjectTemplateCategory",
    "ProjectVisibility",
]
