"""Repositories for the configuration management service, one per model."""

from __future__ import annotations

from app.repositories.configuration_ansible_inventory import ConfigurationAnsibleInventoryRepository
from app.repositories.configuration_approval import ConfigurationApprovalRepository
from app.repositories.configuration_assignment import ConfigurationAssignmentRepository
from app.repositories.configuration_audit import ConfigurationAuditRepository
from app.repositories.configuration_backup import ConfigurationBackupRepository
from app.repositories.configuration_baseline import ConfigurationBaselineRepository
from app.repositories.configuration_change_set import ConfigurationChangeSetRepository
from app.repositories.configuration_compliance import ConfigurationComplianceRepository
from app.repositories.configuration_drift import ConfigurationDriftRepository
from app.repositories.configuration_environment import ConfigurationEnvironmentRepository
from app.repositories.configuration_git_repository import ConfigurationGitRepositoryRepository
from app.repositories.configuration_kubernetes_manifest import (
    ConfigurationKubernetesManifestRepository,
)
from app.repositories.configuration_policy import ConfigurationPolicyRepository
from app.repositories.configuration_profile import ConfigurationProfileRepository
from app.repositories.configuration_report import ConfigurationReportRepository
from app.repositories.configuration_restore_job import ConfigurationRestoreJobRepository
from app.repositories.configuration_rollback import ConfigurationRollbackRepository
from app.repositories.configuration_statistics import ConfigurationStatisticsRepository
from app.repositories.configuration_template import ConfigurationTemplateRepository
from app.repositories.configuration_tosca_template import ConfigurationToscaTemplateRepository
from app.repositories.configuration_variable import ConfigurationVariableRepository
from app.repositories.configuration_version import ConfigurationVersionRepository

__all__ = [
    "ConfigurationAnsibleInventoryRepository",
    "ConfigurationApprovalRepository",
    "ConfigurationAssignmentRepository",
    "ConfigurationAuditRepository",
    "ConfigurationBackupRepository",
    "ConfigurationBaselineRepository",
    "ConfigurationChangeSetRepository",
    "ConfigurationComplianceRepository",
    "ConfigurationDriftRepository",
    "ConfigurationEnvironmentRepository",
    "ConfigurationGitRepositoryRepository",
    "ConfigurationKubernetesManifestRepository",
    "ConfigurationPolicyRepository",
    "ConfigurationProfileRepository",
    "ConfigurationReportRepository",
    "ConfigurationRestoreJobRepository",
    "ConfigurationRollbackRepository",
    "ConfigurationStatisticsRepository",
    "ConfigurationTemplateRepository",
    "ConfigurationToscaTemplateRepository",
    "ConfigurationVariableRepository",
    "ConfigurationVersionRepository",
]
