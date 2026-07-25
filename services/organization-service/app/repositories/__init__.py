"""Repositories for the organization service, one per model."""

from __future__ import annotations

from app.repositories.activity import OrganizationActivityRepository
from app.repositories.audit import OrganizationAuditRepository
from app.repositories.business_unit import BusinessUnitRepository
from app.repositories.department import DepartmentRepository
from app.repositories.invitation import OrganizationInvitationRepository
from app.repositories.member import OrganizationMemberRepository
from app.repositories.organization import OrganizationRepository
from app.repositories.organization_branding import OrganizationBrandingRepository
from app.repositories.organization_domain import OrganizationDomainRepository
from app.repositories.organization_license import OrganizationLicenseRepository
from app.repositories.organization_limits import OrganizationLimitsRepository
from app.repositories.organization_metadata import OrganizationMetadataRepository
from app.repositories.organization_preferences import OrganizationPreferencesRepository
from app.repositories.organization_quota import OrganizationQuotaRepository
from app.repositories.organization_settings import OrganizationSettingsRepository
from app.repositories.organization_subscription import OrganizationSubscriptionRepository
from app.repositories.statistics import OrganizationStatisticsRepository
from app.repositories.tag import OrganizationTagRepository
from app.repositories.team import TeamRepository

__all__ = [
    "BusinessUnitRepository",
    "DepartmentRepository",
    "OrganizationActivityRepository",
    "OrganizationAuditRepository",
    "OrganizationBrandingRepository",
    "OrganizationDomainRepository",
    "OrganizationInvitationRepository",
    "OrganizationLicenseRepository",
    "OrganizationLimitsRepository",
    "OrganizationMemberRepository",
    "OrganizationMetadataRepository",
    "OrganizationPreferencesRepository",
    "OrganizationQuotaRepository",
    "OrganizationRepository",
    "OrganizationSettingsRepository",
    "OrganizationStatisticsRepository",
    "OrganizationSubscriptionRepository",
    "OrganizationTagRepository",
    "TeamRepository",
]
