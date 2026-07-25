"""Repositories for the project service, one per model."""

from __future__ import annotations

from app.repositories.project import ProjectRepository
from app.repositories.project_activity import ProjectActivityRepository
from app.repositories.project_archive import ProjectArchiveRepository
from app.repositories.project_audit import ProjectAuditRepository
from app.repositories.project_export_job import ProjectExportJobRepository
from app.repositories.project_favorite import ProjectFavoriteRepository
from app.repositories.project_import_job import ProjectImportJobRepository
from app.repositories.project_integration import ProjectIntegrationRepository
from app.repositories.project_label import ProjectLabelRepository
from app.repositories.project_member import ProjectMemberRepository
from app.repositories.project_metadata import ProjectMetadataRepository
from app.repositories.project_note import ProjectNoteRepository
from app.repositories.project_preferences import ProjectPreferencesRepository
from app.repositories.project_resource import ProjectResourceRepository
from app.repositories.project_role import ProjectRoleRepository
from app.repositories.project_settings import ProjectSettingsRepository
from app.repositories.project_statistics import ProjectStatisticsRepository
from app.repositories.project_tag import ProjectTagRepository
from app.repositories.project_template import ProjectTemplateRepository

__all__ = [
    "ProjectActivityRepository",
    "ProjectArchiveRepository",
    "ProjectAuditRepository",
    "ProjectExportJobRepository",
    "ProjectFavoriteRepository",
    "ProjectImportJobRepository",
    "ProjectIntegrationRepository",
    "ProjectLabelRepository",
    "ProjectMemberRepository",
    "ProjectMetadataRepository",
    "ProjectNoteRepository",
    "ProjectPreferencesRepository",
    "ProjectRepository",
    "ProjectResourceRepository",
    "ProjectRoleRepository",
    "ProjectSettingsRepository",
    "ProjectStatisticsRepository",
    "ProjectTagRepository",
    "ProjectTemplateRepository",
]
