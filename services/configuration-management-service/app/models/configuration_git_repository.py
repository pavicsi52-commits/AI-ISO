"""``configuration_git_repositories`` table. Per docs/039 "GITOPS"
"Support": GitHub, GitLab, Azure DevOps, Bitbucket, Gitea, Branch
Tracking, Pull Requests, Commit History, Webhook Integration,
Synchronization, Conflict Detection.

Per docs/039's own SECURITY section ("Secrets SHALL always be
referenced through the Secrets Management Service"),
:attr:`credential_ref`/:attr:`webhook_secret_ref` store only a
``services/secrets-management-service`` reference id, never a raw
token/secret.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import GitProvider, GitSyncStatus


class ConfigurationGitRepository(BaseModel):
    """One Git repository backing a configuration profile's GitOps workflow."""

    __tablename__ = "configuration_git_repositories"

    profile_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("configuration_profiles.id", ondelete="SET NULL"), default=None, index=True
    )
    provider: Mapped[GitProvider] = mapped_column(String(16), index=True)
    repository_url: Mapped[str] = mapped_column(String(1024))
    branch: Mapped[str] = mapped_column(String(128), default="main")
    sync_status: Mapped[GitSyncStatus] = mapped_column(
        String(16), default=GitSyncStatus.PENDING, index=True
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    credential_ref: Mapped[str | None] = mapped_column(String(255), default=None)
    webhook_secret_ref: Mapped[str | None] = mapped_column(String(255), default=None)


__all__ = ["ConfigurationGitRepository"]
