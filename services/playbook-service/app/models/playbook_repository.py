"""``playbook_repository`` table -- a named grouping playbooks are filed
into (distinct from a Git repository), per docs/041 "REPOSITORY"
"Support": Folder Organization, Shared Repository, Organization
Repository, Project Repository.

Named :class:`PlaybookRepositoryFolder`, not ``PlaybookRepository`` --
that name is reserved for this model's own
:class:`~shared_core.database.repository.BaseRepository` subclass,
``PlaybookRepositoryFolderRepository`` (``app/repositories
/playbook_repository.py``), the same "disambiguate rather than
collide" precedent ``services/configuration-management-service``'s own
``ConfigurationGitRepository`` (a Git repo entity, distinct from that
service's own repository-pattern classes) already established.
"""

from __future__ import annotations

from shared_core.database.base import BaseModel
from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import RepositoryType, RepositoryVisibility


class PlaybookRepositoryFolder(BaseModel):
    """One named grouping of playbooks."""

    __tablename__ = "playbook_repository"

    name: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    repository_type: Mapped[RepositoryType] = mapped_column(String(16), index=True)
    visibility: Mapped[RepositoryVisibility] = mapped_column(
        String(16), default=RepositoryVisibility.PRIVATE
    )


__all__ = ["PlaybookRepositoryFolder"]
