"""Small, dependency-free utility functions shared across the framework."""

from __future__ import annotations

_UNITS = ("B", "KB", "MB", "GB", "TB", "PB")
_BYTES_PER_UNIT: float = 1024.0


def bytes_to_human_readable(num_bytes: float) -> str:
    """Format a byte count as a human-readable string (e.g. ``"1.5 GB"``)."""
    value = float(num_bytes)
    for unit in _UNITS:
        if abs(value) < _BYTES_PER_UNIT:
            return f"{value:.1f} {unit}"
        value /= _BYTES_PER_UNIT
    return f"{value:.1f} EB"


__all__ = ["bytes_to_human_readable"]
