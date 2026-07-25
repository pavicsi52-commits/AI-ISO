"""Log retention: automatic cleanup of rotated log files past their retention window.

``SizeAndTimeRotatingHandler``'s ``backup_count`` already bounds the
*number* of rotated files kept; this covers the complementary
*age*-based policy docs/014_Enterprise_Logging_Framework.md.txt
"LOG ROTATION" also asks for ("Retention Policy", "Automatic Cleanup").
A pure function, not a scheduled job -- AI-IOS services call it from
whatever scheduling mechanism they already have (see
docs/014_Enterprise_Logging_Framework.md.txt "DO NOT IMPLEMENT: Business Logic").
"""

from __future__ import annotations

import time
from pathlib import Path

from shared_core.logging.constants import LoggingFrameworkConstants


def cleanup_old_logs(
    directory: Path,
    *,
    retention_days: int = LoggingFrameworkConstants.DEFAULT_RETENTION_DAYS,
    pattern: str = "*.log*",
) -> list[Path]:
    """Delete rotated log files in *directory* older than *retention_days*.

    Returns the list of files removed. Missing directories are treated as
    having nothing to clean up rather than an error.
    """
    if not directory.is_dir():
        return []

    cutoff = time.time() - (retention_days * 86_400)
    removed: list[Path] = []
    for path in directory.glob(pattern):
        if path.is_file() and path.stat().st_mtime < cutoff:
            path.unlink()
            removed.append(path)
    return removed
