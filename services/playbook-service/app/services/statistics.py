"""Playbook repository statistics computation. Per docs/041 "ANALYTICS"
"Collect": Playbook Count, Execution References, Downloads, Approvals,
Validation Results, Version Growth, Most Used Content, Deprecated
Content. Computed on demand and cached, the same "cached, not live"
shape ``services/automation-service``'s own ``AutomationStatisticsService``
established.

**Downloads**/**Execution References**: no download- or execution-
tracking mechanism exists anywhere in this service's own data model
(distribution/execution are, per docs/041's own "OBJECTIVE",
explicitly out of scope -- "Execution belongs to Prompt 040") --
honestly left at ``0`` rather than fabricated, until such a mechanism
exists.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from uuid import UUID

from app.models.enums import PlaybookStatus
from app.models.playbook_statistics import PlaybookStatistics
from app.repositories.playbook import PlaybookRepository
from app.repositories.playbook_approval import PlaybookApprovalRepository
from app.repositories.playbook_statistics import PlaybookStatisticsRepository
from app.repositories.playbook_version import PlaybookVersionRepository
from app.validators.content_validator import validate_content


class PlaybookStatisticsService:
    """Recomputes and reads an organization's cached playbook-repository analytics."""

    def __init__(
        self,
        statistics: PlaybookStatisticsRepository,
        playbooks: PlaybookRepository,
        versions: PlaybookVersionRepository,
        approvals: PlaybookApprovalRepository,
    ) -> None:
        self._statistics = statistics
        self._playbooks = playbooks
        self._versions = versions
        self._approvals = approvals

    async def get_for_org(self, organization_id: UUID) -> PlaybookStatistics:
        """Return *organization_id*'s cached snapshot, recomputing if none exists yet."""
        existing = await self._statistics.get_for_org(organization_id)
        if existing is not None:
            return existing
        return await self.recompute(organization_id)

    async def recompute(self, organization_id: UUID) -> PlaybookStatistics:
        """Recompute and persist *organization_id*'s statistics snapshot."""
        playbooks = await self._playbooks.list_for_org(organization_id)

        total_versions = 0
        version_growth: Counter[str] = Counter()
        validation_results: Counter[str] = Counter()
        for playbook in playbooks:
            versions = await self._versions.list_for_playbook(playbook.id)
            total_versions += len(versions)
            for version in versions:
                version_growth[version.created_at.date().isoformat()] += 1

            latest = await self._versions.get_latest_for_playbook(playbook.id)
            if latest is not None:
                errors = await validate_content(playbook.content_type, latest.content)
                validation_results["passed" if not errors else "failed"] += 1

        approvals_summary: Counter[str] = Counter()
        for playbook in playbooks:
            for approval in await self._approvals.list_for_playbook(playbook.id):
                approvals_summary[str(approval.status)] += 1

        snapshot_fields = {
            "total_playbooks": len(playbooks),
            "total_versions": total_versions,
            "total_downloads": 0,
            "approvals_summary": dict(approvals_summary),
            "validation_results_summary": dict(validation_results),
            "version_growth": dict(version_growth),
            "most_used_content": dict(Counter(str(p.content_type) for p in playbooks)),
            "deprecated_content_count": sum(
                1 for p in playbooks if p.status == PlaybookStatus.DEPRECATED
            ),
            "computed_at": datetime.now(UTC),
        }

        existing = await self._statistics.get_for_org(organization_id)
        if existing is not None:
            for field, value in snapshot_fields.items():
                setattr(existing, field, value)
            return existing
        return await self._statistics.create(
            PlaybookStatistics(organization_id=organization_id, **snapshot_fields)
        )


__all__ = ["PlaybookStatisticsService"]
