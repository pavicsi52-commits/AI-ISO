"""Every repository this service owns."""

from __future__ import annotations

from app.repositories.playbook import PlaybookRepository
from app.repositories.playbook_approval import PlaybookApprovalRepository
from app.repositories.playbook_artifact import PlaybookArtifactRepository
from app.repositories.playbook_audit import PlaybookAuditRepository
from app.repositories.playbook_category import PlaybookCategoryRepository
from app.repositories.playbook_collection import PlaybookCollectionRepository
from app.repositories.playbook_dependency import PlaybookDependencyRepository
from app.repositories.playbook_label import PlaybookLabelRepository
from app.repositories.playbook_report import PlaybookReportRepository
from app.repositories.playbook_repository import PlaybookRepositoryFolderRepository
from app.repositories.playbook_review import PlaybookReviewRepository
from app.repositories.playbook_role import PlaybookRoleRepository
from app.repositories.playbook_script import PlaybookScriptRepository
from app.repositories.playbook_signature import PlaybookSignatureRepository
from app.repositories.playbook_statistics import PlaybookStatisticsRepository
from app.repositories.playbook_tag import PlaybookTagRepository
from app.repositories.playbook_template import PlaybookTemplateRepository
from app.repositories.playbook_variable import PlaybookVariableRepository
from app.repositories.playbook_version import PlaybookVersionRepository

__all__ = [
    "PlaybookApprovalRepository",
    "PlaybookArtifactRepository",
    "PlaybookAuditRepository",
    "PlaybookCategoryRepository",
    "PlaybookCollectionRepository",
    "PlaybookDependencyRepository",
    "PlaybookLabelRepository",
    "PlaybookReportRepository",
    "PlaybookRepository",
    "PlaybookRepositoryFolderRepository",
    "PlaybookReviewRepository",
    "PlaybookRoleRepository",
    "PlaybookScriptRepository",
    "PlaybookSignatureRepository",
    "PlaybookStatisticsRepository",
    "PlaybookTagRepository",
    "PlaybookTemplateRepository",
    "PlaybookVariableRepository",
    "PlaybookVersionRepository",
]
