"""Enterprise Database Framework.

Every future microservice inherits database connections, transactions,
repositories, unit of work, pagination, sorting, filtering, soft delete,
audit, versioning, tenant isolation, query utilities, and health checks
from this package rather than reimplementing them
(docs/018_Enterprise_Database_Framework.md.txt "OBJECTIVE"). PostgreSQL
only. No business tables, no business logic.

Decorators (``@transaction``, ``@readonly``, ``@tenant``, ``@audit``,
``@soft_delete``, ``@retry``) and the seed decorator (``@seed``) are
imported from their own submodules
(:mod:`shared_core.database.decorators`, :mod:`shared_core.database.seed`)
rather than re-exported here -- their names would otherwise shadow this
package's own ``transaction``/``seed`` submodule attributes. For the same
reason, the low-level ``unit_of_work()`` context-manager function stays at
:func:`shared_core.database.transaction.unit_of_work` rather than being
re-exported here -- this package already has a same-named
:mod:`shared_core.database.unit_of_work` submodule (home of the
higher-level :class:`UnitOfWork` class, which *is* exported here).
"""

from shared_core.database.audit import (
    AuditEntry,
    capture_before,
    record_audit,
    record_bulk_audit,
    snapshot,
)
from shared_core.database.base import Base, BaseModel
from shared_core.database.connection import graceful_shutdown, wait_for_database
from shared_core.database.engine import (
    create_engine,
    create_engine_from_pool_settings,
    create_test_engine,
)
from shared_core.database.exceptions import (
    ConnectionFailedError,
    ConstraintFailedError,
    DuplicateRecordError,
    MigrationFailedError,
    QueryTimeoutError,
    RepositoryError,
    TenantViolationError,
    TransactionFailedError,
    VersionConflictError,
)
from shared_core.database.factory import (
    DatabaseFramework,
    create_database_framework,
    create_test_database_framework,
)
from shared_core.database.filtering import Filter, FilterOperator, apply_filter, apply_filters
from shared_core.database.fixtures import ModelFactory
from shared_core.database.health import (
    DatabaseHealthReport,
    PoolStatus,
    check_database_health,
    get_health_report,
    get_pool_status,
)
from shared_core.database.migration import (
    MigrationStatus,
    build_alembic_config,
    downgrade,
    generate_revision,
    get_current_revision,
    get_current_revision_async,
    get_head_revision,
    get_migration_history,
    get_migration_status,
    sync_dsn,
    upgrade,
    validate_migrations,
)
from shared_core.database.pagination import (
    CursorPage,
    PageRequest,
    PaginatedResult,
    PaginationMetadata,
    decode_cursor,
    encode_cursor,
    paginate_by_cursor,
    paginate_by_offset,
)
from shared_core.database.query import QueryBuilder
from shared_core.database.repository import BaseRepository
from shared_core.database.search import SearchMode, apply_search
from shared_core.database.seed import SeedDefinition, SeedEnvironment, SeedRegistry
from shared_core.database.session import (
    create_session_factory,
    get_session,
    get_worker_session,
    session_scope,
)
from shared_core.database.settings import ConnectionPoolSettings, build_pool_settings
from shared_core.database.soft_delete import SoftDeletable, mark_deleted, mark_restored, purge
from shared_core.database.sorting import (
    NullsPosition,
    SortDirection,
    SortField,
    apply_sorting,
    parse_sort_expression,
)
from shared_core.database.tenant import (
    TenantScope,
    apply_tenant_scope,
    enforce_tenant_match,
    tenant_scope_from_security_context,
)
from shared_core.database.transaction import is_retryable_error, nested_transaction, run_with_retry
from shared_core.database.unit_of_work import UnitOfWork
from shared_core.database.versioning import Versioned, check_version, increment_version

__all__ = [
    "AuditEntry",
    "Base",
    "BaseModel",
    "BaseRepository",
    "ConnectionFailedError",
    "ConnectionPoolSettings",
    "ConstraintFailedError",
    "CursorPage",
    "DatabaseFramework",
    "DatabaseHealthReport",
    "DuplicateRecordError",
    "Filter",
    "FilterOperator",
    "MigrationFailedError",
    "MigrationStatus",
    "ModelFactory",
    "NullsPosition",
    "PageRequest",
    "PaginatedResult",
    "PaginationMetadata",
    "PoolStatus",
    "QueryBuilder",
    "QueryTimeoutError",
    "RepositoryError",
    "SearchMode",
    "SeedDefinition",
    "SeedEnvironment",
    "SeedRegistry",
    "SoftDeletable",
    "SortDirection",
    "SortField",
    "TenantScope",
    "TenantViolationError",
    "TransactionFailedError",
    "UnitOfWork",
    "VersionConflictError",
    "Versioned",
    "apply_filter",
    "apply_filters",
    "apply_search",
    "apply_sorting",
    "apply_tenant_scope",
    "build_alembic_config",
    "build_pool_settings",
    "capture_before",
    "check_database_health",
    "check_version",
    "create_database_framework",
    "create_engine",
    "create_engine_from_pool_settings",
    "create_session_factory",
    "create_test_database_framework",
    "create_test_engine",
    "decode_cursor",
    "downgrade",
    "encode_cursor",
    "enforce_tenant_match",
    "generate_revision",
    "get_current_revision",
    "get_current_revision_async",
    "get_head_revision",
    "get_health_report",
    "get_migration_history",
    "get_migration_status",
    "get_pool_status",
    "get_session",
    "get_worker_session",
    "graceful_shutdown",
    "increment_version",
    "is_retryable_error",
    "mark_deleted",
    "mark_restored",
    "nested_transaction",
    "paginate_by_cursor",
    "paginate_by_offset",
    "parse_sort_expression",
    "purge",
    "record_audit",
    "record_bulk_audit",
    "run_with_retry",
    "session_scope",
    "snapshot",
    "sync_dsn",
    "tenant_scope_from_security_context",
    "upgrade",
    "validate_migrations",
    "wait_for_database",
]
