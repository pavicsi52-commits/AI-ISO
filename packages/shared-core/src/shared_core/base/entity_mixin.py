"""Combined base entity mixin.

Composes every mixin in this package into the standard column set every
AI-IOS entity table carries, per docs/007_Database_Master_Architecture.md.txt
"STANDARD COLUMNS": id, created_at, updated_at, deleted_at, created_by,
updated_by, deleted_by, version, is_active, organization_id, project_id.
"""

from __future__ import annotations

from shared_core.base.audit_mixin import AuditMixin
from shared_core.base.soft_delete_mixin import SoftDeleteMixin
from shared_core.base.tenant_mixin import TenantMixin
from shared_core.base.timestamp_mixin import TimestampMixin
from shared_core.base.uuid_mixin import UUIDMixin
from shared_core.base.version_mixin import VersionMixin


class BaseEntityMixin(
    UUIDMixin,
    TimestampMixin,
    AuditMixin,
    SoftDeleteMixin,
    VersionMixin,
    TenantMixin,
):
    """Standard column set for every tenant-scoped AI-IOS entity table."""
