"""Small, dependency-free trace/span identifier utilities."""

from __future__ import annotations

_TRACE_ID_HEX_LENGTH = 32
_SPAN_ID_HEX_LENGTH = 16


def format_trace_id(trace_id: int) -> str:
    """Format an integer trace ID as the standard 32-character lowercase hex string."""
    return format(trace_id, "032x")


def format_span_id(span_id: int) -> str:
    """Format an integer span ID as the standard 16-character lowercase hex string."""
    return format(span_id, "016x")


def is_valid_trace_id(trace_id: str) -> bool:
    """Whether *trace_id* is a well-formed, non-zero 32-character hex string."""
    return _is_valid_hex_id(trace_id, _TRACE_ID_HEX_LENGTH)


def is_valid_span_id(span_id: str) -> bool:
    """Whether *span_id* is a well-formed, non-zero 16-character hex string."""
    return _is_valid_hex_id(span_id, _SPAN_ID_HEX_LENGTH)


def _is_valid_hex_id(value: str, expected_length: int) -> bool:
    if len(value) != expected_length:
        return False
    try:
        parsed = int(value, 16)
    except ValueError:
        return False
    return parsed != 0


__all__ = ["format_span_id", "format_trace_id", "is_valid_span_id", "is_valid_trace_id"]
