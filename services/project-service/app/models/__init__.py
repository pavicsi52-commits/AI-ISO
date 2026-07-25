"""SQLAlchemy models for the project service.

Every model must be imported here so it registers with
:data:`shared_core.database.base.Base.metadata` -- both Alembic
autogenerate and any create_all() call rely on every table being
known before they run.
"""

from __future__ import annotations

from app.models.project import Project
from app.models.project_activity import ProjectActivity
from app.models.project_archive import ProjectArchive
from app.models.project_audit import ProjectAuditEntry
from app.models.project_export_job import ProjectExportJob
from app.models.project_favorite import ProjectFavorite
from app.models.project_import_job import ProjectImportJob
from app.models.project_integration import ProjectIntegration
from app.models.project_label import ProjectLabel
from app.models.project_member import ProjectMember
from app.models.project_metadata import ProjectMetadataEntry
from app.models.project_note import ProjectNote
from app.models.project_preferences import ProjectPreferences
from app.models.project_resource import ProjectResource
from app.models.project_role import ProjectRole
from app.models.project_settings import ProjectSettings
from app.models.project_statistics import ProjectStatistics
from app.models.project_tag import ProjectTag
from app.models.project_template import ProjectTemplate

__all__ = [
    "Project",
    "ProjectActivity",
    "ProjectArchive",
    "ProjectAuditEntry",
    "ProjectExportJob",
    "ProjectFavorite",
    "ProjectImportJob",
    "ProjectIntegration",
    "ProjectLabel",
    "ProjectMember",
    "ProjectMetadataEntry",
    "ProjectNote",
    "ProjectPreferences",
    "ProjectResource",
    "ProjectRole",
    "ProjectSettings",
    "ProjectStatistics",
    "ProjectTag",
    "ProjectTemplate",
]
