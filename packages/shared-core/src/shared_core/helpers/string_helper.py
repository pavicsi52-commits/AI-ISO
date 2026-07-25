"""String manipulation helper functions."""

from __future__ import annotations

import re
import unicodedata

_SLUG_INVALID_CHARS = re.compile(r"[^a-z0-9]+")
_CAMEL_TO_SNAKE = re.compile(r"(?<!^)(?=[A-Z])")


def slugify(value: str) -> str:
    """Convert a string into a lowercase, hyphen-separated slug."""
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    slug = _SLUG_INVALID_CHARS.sub("-", normalized.lower()).strip("-")
    return slug


def truncate(value: str, max_length: int, *, suffix: str = "...") -> str:
    """Truncate ``value`` to ``max_length`` characters, appending ``suffix`` if cut."""
    if len(value) <= max_length:
        return value
    return value[: max_length - len(suffix)] + suffix


def to_snake_case(value: str) -> str:
    """Convert a CamelCase or PascalCase string to snake_case."""
    return _CAMEL_TO_SNAKE.sub("_", value).lower()


def mask_string(value: str, *, visible_chars: int = 4, mask_char: str = "*") -> str:
    """Mask all but the last ``visible_chars`` characters of a string."""
    if len(value) <= visible_chars:
        return mask_char * len(value)
    return mask_char * (len(value) - visible_chars) + value[-visible_chars:]
