"""Configuration management statistics/analytics computation. Per
docs/039 "ANALYTICS" "Collect": Profile Count, Version Count, Drift
Statistics, Compliance Scores, Rollback Statistics, Deployment
Readiness, Environment Distribution, Change Frequency. Computed on
demand and cached, the same "cached, not live" shape
``services/asset-management-service``'s own ``asset_statistics``
established.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from uuid import UUID

from app.models.configuration_statistics import ConfigurationStatistics
from app.models.enums import ProfileStatus
from app.repositories.configuration_change_set import ConfigurationChangeSetRepository
from app.repositories.configuration_compliance import ConfigurationComplianceRepository
from app.repositories.configuration_drift import ConfigurationDriftRepository
from app.repositories.configuration_profile import ConfigurationProfileRepository
from app.repositories.configuration_rollback import ConfigurationRollbackRepository
from app.repositories.configuration_statistics import ConfigurationStatisticsRepository
from app.repositories.configuration_version import ConfigurationVersionRepository


class ConfigurationStatisticsService:
    """Recomputes and reads an organization's cached configuration-management analytics."""

    def __init__(
        self,
        statistics: ConfigurationStatisticsRepository,
        profiles: ConfigurationProfileRepository,
        versions: ConfigurationVersionRepository,
        drift: ConfigurationDriftRepository,
        compliance: ConfigurationComplianceRepository,
        rollbacks: ConfigurationRollbackRepository,
        change_sets: ConfigurationChangeSetRepository,
    ) -> None:
        self._statistics = statistics
        self._profiles = profiles
        self._versions = versions
        self._drift = drift
        self._compliance = compliance
        self._rollbacks = rollbacks
        self._change_sets = change_sets

    async def get_for_org(self, organization_id: UUID) -> ConfigurationStatistics:
        """Return *organization_id*'s cached snapshot, recomputing if none exists yet."""
        existing = await self._statistics.get_for_org(organization_id)
        if existing is not None:
            return existing
        return await self.recompute(organization_id)

    async def recompute(self, organization_id: UUID) -> ConfigurationStatistics:
        """Recompute and persist *organization_id*'s statistics snapshot."""
        profiles = await self._profiles.list_for_org(organization_id)

        total_versions = 0
        compliance_counter: Counter[str] = Counter()
        rollback_counter: Counter[str] = Counter()
        change_counter: Counter[str] = Counter()
        for profile in profiles:
            total_versions += len(await self._versions.list_for_profile(profile.id))
            for entry in await self._compliance.list_for_profile(profile.id):
                compliance_counter[str(entry.status)] += 1
            for rollback in await self._rollbacks.list_for_profile(profile.id):
                rollback_counter[str(rollback.status)] += 1
            for change_set in await self._change_sets.list_for_profile(profile.id):
                change_counter[str(change_set.status)] += 1

        unresolved_drift = await self._drift.list_unresolved_for_org(organization_id)
        drift_statistics = {
            "unresolved_total": len(unresolved_drift),
            "by_type": dict(Counter(str(entry.drift_type) for entry in unresolved_drift)),
        }

        snapshot_fields = {
            "total_profiles": len(profiles),
            "total_versions": total_versions,
            "drift_statistics": drift_statistics,
            "compliance_scores": dict(compliance_counter),
            "rollback_statistics": dict(rollback_counter),
            "deployment_readiness": {
                "active_profiles": sum(1 for p in profiles if p.status == ProfileStatus.ACTIVE),
                "draft_profiles": sum(1 for p in profiles if p.status == ProfileStatus.DRAFT),
                "total_profiles": len(profiles),
            },
            "environment_distribution": dict(Counter(str(p.environment) for p in profiles)),
            "change_frequency": dict(change_counter),
            "computed_at": datetime.now(UTC),
        }

        existing = await self._statistics.get_for_org(organization_id)
        if existing is not None:
            for field, value in snapshot_fields.items():
                setattr(existing, field, value)
            return existing
        return await self._statistics.create(
            ConfigurationStatistics(organization_id=organization_id, **snapshot_fields)
        )


__all__ = ["ConfigurationStatisticsService"]
