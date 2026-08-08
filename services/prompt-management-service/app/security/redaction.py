"""Secret and PII pattern detection.

Rewritten here rather than imported from ``ai-agent-platform-service``
or ``ai-assistant-service``, per this platform's own zero-cross-service
-import convention: services never share code, only ``shared_core``.
The pattern set is the same one every AI-IOS guardrail module uses,
because the things worth detecting have not changed.

**This module reports what it found, never the matched text.** A
finding that quoted the secret it detected would write that secret into
``prompt_security_scans.findings``, into every backup of that table,
and into any log line rendering it -- defeating the entire point of
detecting it. :func:`redact` returns a masked copy for the callers that
need one; :func:`detect` returns only pattern names.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

REDACTION_PLACEHOLDER = "[REDACTED]"

_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "private_key",
        re.compile(
            r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----.*?"
            r"-----END (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----",
            re.DOTALL,
        ),
    ),
    ("aws_access_key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    (
        "connection_string_password",
        re.compile(
            r"(?i)\b(?:postgres|postgresql|mysql|mongodb|redis|amqp)(?:\+\w+)?://"
            r"[^\s:@/]+:([^\s@]+)(?=@)"
        ),
    ),
    (
        "assigned_secret",
        re.compile(
            r"(?i)\b(?:api[_-]?key|secret|password|passwd|token|credential)\b\s*[:=]\s*"
            r"[\"']?([^\s\"',;]{6,})[\"']?"
        ),
    ),
    ("bearer_token", re.compile(r"(?i)\bbearer\s+([A-Za-z0-9._\-]{16,})")),
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("credit_card", re.compile(r"\b(?:\d[ -]*?){13,19}\b")),
    ("ipv4", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
)

_GROUPED = frozenset({"connection_string_password", "assigned_secret", "bearer_token"})
"""Patterns that match a surrounding context and capture only the
secret itself in group 1 -- redacting the whole match would delete the
``api_key=`` label that tells a reader what was removed."""

_PII_KINDS = frozenset({"email", "credit_card", "ipv4"})
"""Findings that are personal data rather than credentials. Split out
so the scanner can grade them differently: a secret in a prompt is
always critical, an email address usually is not."""


@dataclass(frozen=True, slots=True)
class RedactionResult:
    """A masked copy of some text and which pattern kinds fired."""

    text: str
    redacted_kinds: tuple[str, ...] = ()

    @property
    def was_redacted(self) -> bool:
        """Whether anything at all was masked."""
        return bool(self.redacted_kinds)


def detect(text: str) -> tuple[str, ...]:
    """Every pattern kind present in *text*, sorted and deduplicated.

    Returns only the kind names -- never the matched values. This is
    what the security scanner records.
    """
    return tuple(sorted({name for name, pattern in _PATTERNS if pattern.search(text)}))


def is_pii(kind: str) -> bool:
    """Whether *kind* is personal data rather than a credential."""
    return kind in _PII_KINDS


def redact(text: str) -> RedactionResult:
    """Return *text* with every detected secret or PII value masked.

    For grouped patterns only the captured secret is replaced, so
    ``api_key=abc123`` becomes ``api_key=[REDACTED]`` rather than
    vanishing entirely -- a reader can still see that a key was present
    and where.
    """
    redacted = text
    kinds: list[str] = []

    for name, pattern in _PATTERNS:
        if not pattern.search(redacted):
            continue
        kinds.append(name)
        if name in _GROUPED:
            redacted = pattern.sub(
                lambda match: match.group(0).replace(match.group(1), REDACTION_PLACEHOLDER),
                redacted,
            )
        else:
            redacted = pattern.sub(REDACTION_PLACEHOLDER, redacted)

    return RedactionResult(text=redacted, redacted_kinds=tuple(sorted(set(kinds))))


def mask_values(values: dict[str, object], masked_names: set[str]) -> dict[str, object]:
    """Mask the named entries of a variable set.

    Backs ``PromptVariable.is_masked`` and every ``SECRET_REFERENCE``
    variable: the rendered prompt written to ``prompt_executions`` must
    not carry the resolved value, whatever the template did with it.
    """
    return {
        name: (REDACTION_PLACEHOLDER if name in masked_names else value)
        for name, value in values.items()
    }


__all__ = [
    "REDACTION_PLACEHOLDER",
    "RedactionResult",
    "detect",
    "is_pii",
    "mask_values",
    "redact",
]
