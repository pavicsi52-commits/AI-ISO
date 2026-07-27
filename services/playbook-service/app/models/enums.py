"""Enumerations for the playbook service's persisted domain.

Per docs/041 "SUPPORTED CONTENT"/"PLAYBOOK STATUS"/"DEPENDENCIES"/etc.
Sections that enumerate concrete values verbatim are copied exactly;
sections that only name a field or a "Support"/"Collect"/"Generate"
capability list (without a value enumeration) are given a small,
conventional value set documented as derived in that enum's own
docstring -- the same precedent
``services/automation-service``'s own ``app/models/enums.py``
established.
"""

from __future__ import annotations

from enum import StrEnum


class ContentType(StrEnum):
    """Per docs/041 "SUPPORTED CONTENT" (15 values, verbatim)."""

    ANSIBLE_PLAYBOOK = "ansible_playbook"
    ANSIBLE_ROLE = "ansible_role"
    ANSIBLE_COLLECTION = "ansible_collection"
    PYTHON_SCRIPT = "python_script"
    POWERSHELL_SCRIPT = "powershell_script"
    SHELL_SCRIPT = "shell_script"
    BASH_SCRIPT = "bash_script"
    TOSCA_TEMPLATE = "tosca_template"
    CSAR_PACKAGE = "csar_package"
    HELM_CHART = "helm_chart"
    KUBERNETES_YAML = "kubernetes_yaml"
    TERRAFORM_MODULE = "terraform_module"
    CUSTOM_PLUGIN = "custom_plugin"
    WORKFLOW_TEMPLATE = "workflow_template"
    AUTOMATION_TEMPLATE = "automation_template"


class PlaybookStatus(StrEnum):
    """Per docs/041 "PLAYBOOK STATUS" (7 values, verbatim)."""

    DRAFT = "draft"
    REVIEW = "review"
    APPROVED = "approved"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"
    DELETED = "deleted"


class DependencyType(StrEnum):
    """Derived from docs/041 "DEPENDENCIES" "Support" (6 concrete
    dependency kinds; "Circular Dependency Detection" describes
    resolution behavior, not a type of its own).
    """

    PLAYBOOK = "playbook"
    ROLE = "role"
    COLLECTION = "collection"
    PYTHON_PACKAGE = "python_package"
    EXTERNAL_MODULE = "external_module"
    PLUGIN = "plugin"


class ReviewStatus(StrEnum):
    """Derived from docs/041 "APPROVALS" "Support" ("Draft Review"),
    the same pending/in-progress/completed lifecycle shape every prior
    AI-IOS review-shaped workflow established.
    """

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    CHANGES_REQUESTED = "changes_requested"
    COMPLETED = "completed"


class ApprovalType(StrEnum):
    """Per docs/041 "APPROVALS" "Support" (4 values, verbatim; "Draft
    Review" is :class:`ReviewStatus`'s own concern via
    ``playbook_reviews``, not an approval type).
    """

    TECHNICAL = "technical"
    SECURITY = "security"
    OPERATIONAL = "operational"
    PUBLISHING = "publishing"


class ApprovalStatus(StrEnum):
    """Derived from docs/041 "APPROVALS" "Support" ("Approval
    History"/"Revisions" describe behavior, not a status of their
    own), the same lifecycle shape
    ``services/configuration-management-service``'s own
    ``ApprovalStatus`` established.
    """

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class RepositoryType(StrEnum):
    """Per docs/041 "REPOSITORY" "Support" (3 values, verbatim: Shared
    Repository, Organization Repository, Project Repository).
    """

    SHARED = "shared"
    ORGANIZATION = "organization"
    PROJECT = "project"


class RepositoryVisibility(StrEnum):
    """Derived from docs/041 "REPOSITORY" "Support" ("Clone"/"Fork"
    presuppose a visibility concept), the same public/private
    convention every prior AI-IOS content-repository shape established.
    """

    PRIVATE = "private"
    ORGANIZATION = "organization"
    PUBLIC = "public"


class SignatureAlgorithm(StrEnum):
    """Per docs/041 "SECURITY" "Support" ("Digital Signatures").
    Ed25519 -- the modern, fast, small-signature standard for
    content-signing use cases (matching the same
    ``cryptography.hazmat.primitives.asymmetric.ed25519`` primitive
    ``services/secrets-management-service``'s own ``ssh/keygen.py``
    already uses in this monorepo) -- is the one genuinely implemented
    algorithm.
    """

    ED25519 = "ed25519"


class ArtifactType(StrEnum):
    """Derived from docs/041 "REPOSITORY"/"SECURITY" ("Export",
    "Digital Signatures", "Checksum Validation" each imply a
    distributable output artifact), a small, conventional value set.
    """

    SOURCE_BUNDLE = "source_bundle"
    RENDERED_OUTPUT = "rendered_output"
    SIGNED_PACKAGE = "signed_package"
    CHECKSUM_MANIFEST = "checksum_manifest"


class PlaybookReportType(StrEnum):
    """Per docs/041 "REPORTING" "Generate" (6 values, verbatim)."""

    REPOSITORY = "repository"
    VALIDATION = "validation"
    APPROVAL = "approval"
    VERSION = "version"
    DEPENDENCY = "dependency"
    EXECUTIVE_DASHBOARD = "executive_dashboard"


class AuditOutcome(StrEnum):
    """Reused ``SUCCESS``/``FAILURE`` shape, the same convention every
    prior AI-IOS audit-trail table established.
    """

    SUCCESS = "success"
    FAILURE = "failure"


__all__ = [
    "ApprovalStatus",
    "ApprovalType",
    "ArtifactType",
    "AuditOutcome",
    "ContentType",
    "DependencyType",
    "PlaybookReportType",
    "PlaybookStatus",
    "RepositoryType",
    "RepositoryVisibility",
    "ReviewStatus",
    "SignatureAlgorithm",
]
