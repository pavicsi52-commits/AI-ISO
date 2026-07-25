"""SQLAlchemy models for the configuration management service, one per table.

Importing this module registers every table with
:data:`shared_core.database.base.Base.metadata`, which Alembic's
``env.py`` depends on for autogenerate support.
"""

from __future__ import annotations

from app.models.configuration_ansible_inventory import ConfigurationAnsibleInventory
from app.models.configuration_approval import ConfigurationApproval
from app.models.configuration_assignment import ConfigurationAssignment
from app.models.configuration_audit import ConfigurationAuditEntry
from app.models.configuration_backup import ConfigurationBackup
from app.models.configuration_baseline import ConfigurationBaseline
from app.models.configuration_change_set import ConfigurationChangeSet
from app.models.configuration_compliance import ConfigurationCompliance
from app.models.configuration_drift import ConfigurationDrift
from app.models.configuration_environment import ConfigurationEnvironment
from app.models.configuration_git_repository import ConfigurationGitRepository
from app.models.configuration_kubernetes_manifest import ConfigurationKubernetesManifest
from app.models.configuration_policy import ConfigurationPolicy
from app.models.configuration_profile import ConfigurationProfile
from app.models.configuration_report import ConfigurationReport
from app.models.configuration_restore_job import ConfigurationRestoreJob
from app.models.configuration_rollback import ConfigurationRollback
from app.models.configuration_statistics import ConfigurationStatistics
from app.models.configuration_template import ConfigurationTemplate
from app.models.configuration_tosca_template import ConfigurationToscaTemplate
from app.models.configuration_variable import ConfigurationVariable
from app.models.configuration_version import ConfigurationVersion

__all__ = [
    "ConfigurationAnsibleInventory",
    "ConfigurationApproval",
    "ConfigurationAssignment",
    "ConfigurationAuditEntry",
    "ConfigurationBackup",
    "ConfigurationBaseline",
    "ConfigurationChangeSet",
    "ConfigurationCompliance",
    "ConfigurationDrift",
    "ConfigurationEnvironment",
    "ConfigurationGitRepository",
    "ConfigurationKubernetesManifest",
    "ConfigurationPolicy",
    "ConfigurationProfile",
    "ConfigurationReport",
    "ConfigurationRestoreJob",
    "ConfigurationRollback",
    "ConfigurationStatistics",
    "ConfigurationTemplate",
    "ConfigurationToscaTemplate",
    "ConfigurationVariable",
    "ConfigurationVersion",
]
