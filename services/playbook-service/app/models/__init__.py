"""Every ORM model this service owns, imported once so
``Base.metadata`` sees every table (Alembic autogenerate, ``create_all``
in tests).
"""

from __future__ import annotations

from app.models.playbook import Playbook
from app.models.playbook_approval import PlaybookApproval
from app.models.playbook_artifact import PlaybookArtifact
from app.models.playbook_audit import PlaybookAuditEntry
from app.models.playbook_category import PlaybookCategory
from app.models.playbook_collection import PlaybookCollection
from app.models.playbook_dependency import PlaybookDependency
from app.models.playbook_label import PlaybookLabel
from app.models.playbook_report import PlaybookReport
from app.models.playbook_repository import PlaybookRepositoryFolder
from app.models.playbook_review import PlaybookReview
from app.models.playbook_role import PlaybookRole
from app.models.playbook_script import PlaybookScript
from app.models.playbook_signature import PlaybookSignature
from app.models.playbook_statistics import PlaybookStatistics
from app.models.playbook_tag import PlaybookTag
from app.models.playbook_template import PlaybookTemplate
from app.models.playbook_variable import PlaybookVariable
from app.models.playbook_version import PlaybookVersion

__all__ = [
    "Playbook",
    "PlaybookApproval",
    "PlaybookArtifact",
    "PlaybookAuditEntry",
    "PlaybookCategory",
    "PlaybookCollection",
    "PlaybookDependency",
    "PlaybookLabel",
    "PlaybookReport",
    "PlaybookRepositoryFolder",
    "PlaybookReview",
    "PlaybookRole",
    "PlaybookScript",
    "PlaybookSignature",
    "PlaybookStatistics",
    "PlaybookTag",
    "PlaybookTemplate",
    "PlaybookVariable",
    "PlaybookVersion",
]
