"""Database-framework-specific exceptions.

Each subclasses :class:`shared_core.exceptions.database.DatabaseError` so a
bare ``except DatabaseError`` still catches everything raised anywhere in
this framework. Not registered in :mod:`shared_core.exceptions.constants`'s
central catalog -- that module already depends on
:mod:`shared_core.exceptions.database`, so importing back from here would
cycle. Error codes are still manually kept unique against the rest of the
``AIIOS-DB-*`` range (the same approach
:mod:`shared_core.security.exceptions` uses for ``AIIOS-AUTH-*``).
"""

from __future__ import annotations

from shared_core.exceptions.database import DatabaseError


class ConnectionFailedError(DatabaseError):
    """Raised when a database connection cannot be established after retries."""

    error_code = "AIIOS-DB-0002"
    retryable = True
    default_user_message = "Could not connect to the database. Please try again."


class MigrationFailedError(DatabaseError):
    """Raised when an Alembic migration fails to apply or roll back cleanly."""

    error_code = "AIIOS-DB-0003"
    severity = "critical"
    retryable = False
    default_user_message = "A database migration failed."


class ConstraintFailedError(DatabaseError):
    """Raised when a write violates a check, not-null, or foreign key constraint."""

    error_code = "AIIOS-DB-0004"
    status_code = 409
    severity = "medium"
    retryable = False
    default_user_message = "The request violates a data integrity rule."


class DuplicateRecordError(DatabaseError):
    """Raised when a write violates a uniqueness constraint."""

    error_code = "AIIOS-DB-0005"
    status_code = 409
    severity = "medium"
    retryable = False
    default_user_message = "A record with these values already exists."


class VersionConflictError(DatabaseError):
    """Raised when an optimistic-locking version check fails."""

    error_code = "AIIOS-DB-0006"
    status_code = 409
    severity = "medium"
    retryable = True
    default_user_message = "This record was modified by another request. Please retry."


class TenantViolationError(DatabaseError):
    """Raised when a query or entity crosses tenant (organization/project) boundaries."""

    error_code = "AIIOS-DB-0007"
    status_code = 403
    severity = "critical"
    retryable = False
    default_user_message = "You do not have access to this resource."


class QueryTimeoutError(DatabaseError):
    """Raised when a query exceeds its configured timeout."""

    error_code = "AIIOS-DB-0008"
    status_code = 504
    severity = "high"
    retryable = True
    default_user_message = "The request took too long to process. Please try again."


class TransactionFailedError(DatabaseError):
    """Raised when a transaction fails and cannot be committed, even after retries."""

    error_code = "AIIOS-DB-0009"
    severity = "high"
    retryable = True
    default_user_message = "The operation could not be completed. Please try again."


class RepositoryError(DatabaseError):
    """Raised for repository-level failures not covered by a more specific error."""

    error_code = "AIIOS-DB-0010"
    severity = "high"
    retryable = False
    default_user_message = "The operation could not be completed."


__all__ = [
    "ConnectionFailedError",
    "ConstraintFailedError",
    "DuplicateRecordError",
    "MigrationFailedError",
    "QueryTimeoutError",
    "RepositoryError",
    "TenantViolationError",
    "TransactionFailedError",
    "VersionConflictError",
]
