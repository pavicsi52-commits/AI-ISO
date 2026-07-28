"""Secret and PII redaction ("SAFETY": PII Protection, Secret
Redaction).

Runs over **both** directions: text retrieved or returned by a tool
before it is shown to the model, and the model's own output before it
reaches the user. Redacting only one direction would still leak -- a
secret pulled from a runbook into context can be echoed straight back.

Patterns cover the credential shapes this platform actually handles
(bearer tokens, private keys, connection strings with inline
passwords, AWS keys) plus common PII. This is defence in depth, not a
guarantee: a novel secret format will pass, which is why tool results
are also permission-gated rather than relying on redaction alone.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

REDACTION_PLACEHOLDER = "[REDACTED]"

_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    # Private key blocks -- matched first and whole, since their body
    # would otherwise be partially caught by narrower patterns.
    (
        "private_key",
        re.compile(
            r"-----BEGIN[A-Z ]*PRIVATE KEY-----.*?-----END[A-Z ]*PRIVATE KEY-----",
            re.DOTALL,
        ),
    ),
    ("aws_access_key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")),
    (
        "connection_string_password",
        re.compile(r"(?i)\b([a-z0-9+.-]+://[^\s:/@]+:)([^\s@]+)(@)"),
    ),
    (
        "assigned_secret",
        re.compile(
            r"(?i)\b((?:api[_-]?key|secret|token|password|passwd|pwd|credential)"
            r"\s*[:=]\s*)(\"[^\"]+\"|'[^']+'|[^\s,;]+)"
        ),
    ),
    ("bearer_token", re.compile(r"(?i)\b(bearer\s+)([A-Za-z0-9._~+/=-]{12,})")),
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    (
        "credit_card",
        re.compile(r"\b(?:\d[ -]?){13,19}\b"),
    ),
)

_GROUPED = {"connection_string_password", "assigned_secret", "bearer_token"}
"""Patterns that keep a leading group so the *shape* survives.

``password=hunter2`` becomes ``password=[REDACTED]`` rather than a bare
placeholder: the reader still learns a password was set, which is
genuinely useful when reviewing a config, without learning its value.
"""


@dataclass(frozen=True, slots=True)
class RedactionResult:
    """Redacted text plus what was found."""

    text: str
    redacted_kinds: tuple[str, ...]

    @property
    def was_redacted(self) -> bool:
        """Whether anything at all was removed."""
        return bool(self.redacted_kinds)


def redact(text: str) -> RedactionResult:
    """Redact secrets and PII from *text*.

    Returns the text unchanged (and reports nothing) when clean, so a
    caller can cheaply tell whether a guardrail actually fired.
    """
    if not text:
        return RedactionResult(text=text, redacted_kinds=())

    found: list[str] = []
    redacted = text
    for kind, pattern in _PATTERNS:
        if not pattern.search(redacted):
            continue
        found.append(kind)
        if kind in _GROUPED:
            if kind == "connection_string_password":
                redacted = pattern.sub(rf"\1{REDACTION_PLACEHOLDER}\3", redacted)
            else:
                redacted = pattern.sub(rf"\1{REDACTION_PLACEHOLDER}", redacted)
        else:
            redacted = pattern.sub(REDACTION_PLACEHOLDER, redacted)

    return RedactionResult(text=redacted, redacted_kinds=tuple(found))


__all__ = ["REDACTION_PLACEHOLDER", "RedactionResult", "redact"]
