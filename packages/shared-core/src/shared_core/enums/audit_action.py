"""Audit log action enumeration."""

from enum import StrEnum


class AuditAction(StrEnum):
    """Actions recorded in the audit log."""

    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    LOGIN = "login"
    LOGOUT = "logout"
    LOGIN_FAILED = "login_failed"
    PERMISSION_DENIED = "permission_denied"
    PERMISSION_CHANGED = "permission_changed"
    ROLE_CHANGED = "role_changed"
    PASSWORD_CHANGED = "password_changed"
    SECRET_ACCESSED = "secret_accessed"
    EXECUTE = "execute"
    APPROVE = "approve"
    EXPORT = "export"
    IMPORT = "import"
    RESTORE = "restore"
    BULK_CREATE = "bulk_create"
    BULK_UPDATE = "bulk_update"
    BULK_DELETE = "bulk_delete"
