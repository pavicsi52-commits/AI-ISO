"""Business services for the project service."""

from __future__ import annotations

from app.services.activity import ProjectActivityService
from app.services.archive import ProjectArchiveService
from app.services.audit import ProjectAuditService
from app.services.export_service import ProjectExportService
from app.services.favorite import ProjectFavoriteService
from app.services.import_service import ProjectImportService
from app.services.integration import ProjectIntegrationService
from app.services.label import ProjectLabelService
from app.services.member import ProjectMemberService
from app.services.metadata import ProjectMetadataService
from app.services.note import ProjectNoteService
from app.services.preferences import ProjectPreferencesService
from app.services.project import ProjectService
from app.services.resource import ProjectResourceService
from app.services.role import ProjectRoleService
from app.services.settings import ProjectSettingsService
from app.services.statistics import ProjectStatisticsService
from app.services.tag import ProjectTagService
from app.services.template import ProjectTemplateService

__all__ = [
    "ProjectActivityService",
    "ProjectArchiveService",
    "ProjectAuditService",
    "ProjectExportService",
    "ProjectFavoriteService",
    "ProjectImportService",
    "ProjectIntegrationService",
    "ProjectLabelService",
    "ProjectMemberService",
    "ProjectMetadataService",
    "ProjectNoteService",
    "ProjectPreferencesService",
    "ProjectResourceService",
    "ProjectRoleService",
    "ProjectService",
    "ProjectSettingsService",
    "ProjectStatisticsService",
    "ProjectTagService",
    "ProjectTemplateService",
]
