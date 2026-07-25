"""``secret_leases`` table. Per docs/035 "SECRET LEASING": Temporary
Credentials, Lease Duration, Renew Lease, Revoke Lease, Lease
Expiration, Lease Audit.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import LeaseStatus


class SecretLease(BaseModel):
    """One temporary-credential lease on a secret."""

    __tablename__ = "secret_leases"

    secret_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("secret_vault.id", ondelete="CASCADE"), nullable=False, index=True
    )
    principal_id: Mapped[uuid.UUID] = mapped_column(index=True)
    status: Mapped[LeaseStatus] = mapped_column(String(16), default=LeaseStatus.ACTIVE, index=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    lease_duration_seconds: Mapped[int] = mapped_column(Integer)
    renewed_count: Mapped[int] = mapped_column(Integer, default=0)


__all__ = ["SecretLease"]
