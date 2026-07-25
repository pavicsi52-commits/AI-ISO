"""File helper functions."""

from __future__ import annotations

from pathlib import Path

_BYTES_PER_UNIT = 1024


def get_extension(filename: str) -> str:
    """Return the lowercase file extension (without the dot), or "" if none."""
    return Path(filename).suffix.lstrip(".").lower()


def is_safe_filename(filename: str) -> bool:
    """Return whether ``filename`` is free of path traversal / separators."""
    if not filename or filename in {".", ".."}:
        return False
    return "/" not in filename and "\\" not in filename and not filename.startswith(".")


def human_readable_size(size_bytes: int) -> str:
    """Format a byte count as a human-readable string (e.g. "1.5 MB")."""
    size = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < _BYTES_PER_UNIT or unit == "TB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} {unit}"
        size /= _BYTES_PER_UNIT
    return f"{size:.1f} TB"  # pragma: no cover -- unreachable, loop always returns
