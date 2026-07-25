"""Platform role enumeration."""

from enum import StrEnum


class Role(StrEnum):
    """Built-in platform roles. Custom roles are managed at runtime by the
    security framework (docs/017_Enterprise_Security_Framework.md.txt); this
    enum covers the fixed system roles every organization starts with.
    """

    SUPER_ADMIN = "super_admin"
    ORGANIZATION_ADMIN = "organization_admin"
    PROJECT_ADMIN = "project_admin"
    OPERATOR = "operator"
    VIEWER = "viewer"
    AUDITOR = "auditor"
