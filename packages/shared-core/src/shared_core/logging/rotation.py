"""Log file rotation.

Per docs/014_Enterprise_Logging_Framework.md.txt "LOG ROTATION": daily
*and* max-size rotation, with gzip compression of rotated files. The
standard library offers ``TimedRotatingFileHandler`` (time-based) and
``RotatingFileHandler`` (size-based) as separate classes; AI-IOS needs
both at once, so this combines them into one handler.
"""

from __future__ import annotations

import gzip
import logging.handlers
import shutil
from pathlib import Path

from shared_core.logging.constants import LoggingFrameworkConstants


class SizeAndTimeRotatingHandler(logging.handlers.TimedRotatingFileHandler):
    """Rotates daily (or on the configured interval) *or* once ``max_bytes`` is exceeded.

    Rotated files are gzip-compressed when *compress* is ``True``, via the
    ``rotator``/``namer`` hooks ``TimedRotatingFileHandler`` already
    supports -- no custom rollover-file-naming logic needed.
    """

    def __init__(
        self,
        filename: str,
        *,
        when: str = LoggingFrameworkConstants.DEFAULT_ROTATION_WHEN,
        backup_count: int = LoggingFrameworkConstants.DEFAULT_BACKUP_COUNT,
        max_bytes: int = LoggingFrameworkConstants.DEFAULT_MAX_BYTES,
        compress: bool = True,
        encoding: str = "utf-8",
    ) -> None:
        super().__init__(filename, when=when, backupCount=backup_count, encoding=encoding, utc=True)
        self._max_bytes = max_bytes
        if compress:
            self.rotator = _gzip_rotator
            self.namer = _gzip_namer

    def shouldRollover(self, record: logging.LogRecord) -> int:  # noqa: N802 -- stdlib API name
        """Roll over on the time-based schedule, or once the file exceeds ``max_bytes``."""
        if super().shouldRollover(record):
            return 1
        if self._max_bytes > 0 and self.stream is not None:
            self.stream.seek(0, 2)
            if self.stream.tell() >= self._max_bytes:
                return 1
        return 0


def _gzip_namer(name: str) -> str:
    return name + LoggingFrameworkConstants.ROTATED_FILE_SUFFIX


def _gzip_rotator(source: str, dest: str) -> None:
    with Path(source).open("rb") as source_file, gzip.open(dest, "wb") as dest_file:
        shutil.copyfileobj(source_file, dest_file)
    Path(source).unlink()
