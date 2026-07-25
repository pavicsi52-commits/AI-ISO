"""Reusable SQLAlchemy declarative mixins.

Per docs/012_Shared_Core_Framework.md.txt: "Every future database model
inherits these." Combine with a concrete service's ``DeclarativeBase`` via
multiple inheritance, e.g.::

    class Asset(Base, BaseEntityMixin):
        __tablename__ = "assets"
        name: Mapped[str] = mapped_column()
"""

from shared_core.base.audit_mixin import AuditMixin
from shared_core.base.entity_mixin import BaseEntityMixin
from shared_core.base.soft_delete_mixin import SoftDeleteMixin
from shared_core.base.tenant_mixin import TenantMixin
from shared_core.base.timestamp_mixin import TimestampMixin
from shared_core.base.uuid_mixin import UUIDMixin
from shared_core.base.version_mixin import VersionMixin

__all__ = [
    "AuditMixin",
    "BaseEntityMixin",
    "SoftDeleteMixin",
    "TenantMixin",
    "TimestampMixin",
    "UUIDMixin",
    "VersionMixin",
]
