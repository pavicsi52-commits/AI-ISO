"""Permission action enumeration."""

from enum import StrEnum


class Permission(StrEnum):
    """CRUD and lifecycle actions used by the RBAC engine."""

    READ = "read"
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    EXECUTE = "execute"
    APPROVE = "approve"
    EXPORT = "export"
    IMPORT = "import"
    ADMIN = "admin"
