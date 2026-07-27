"""Response schema for ``GET /playbooks/statistics``. Per docs/041
"ANALYTICS" "Collect": Playbook Count, Execution References, Downloads,
Approvals, Validation Results, Version Growth, Most Used Content,
Deprecated Content.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class PlaybookStatisticsResponse(BaseModel):
    """The current-state playbook-repository analytics rollup."""

    total_playbooks: int
    total_versions: int
    total_downloads: int
    approvals_summary: dict[str, Any]
    validation_results_summary: dict[str, Any]
    version_growth: dict[str, Any]
    most_used_content: dict[str, Any]
    deprecated_content_count: int
    computed_at: datetime


__all__ = ["PlaybookStatisticsResponse"]
