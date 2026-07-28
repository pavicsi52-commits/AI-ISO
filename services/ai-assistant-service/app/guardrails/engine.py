"""The guardrail pipeline ("SAFETY").

Three checks, applied at the points where each actually helps:

- :func:`screen_user_input` -- prompt-injection detection on anything a
  user types.
- :func:`screen_retrieved_context` -- **injection detection plus
  redaction on retrieved documents**. This is the one most often
  skipped and the one that matters most: a runbook or wiki page is
  untrusted input the moment its text enters the model's context, and
  an attacker who can edit a wiki page can otherwise plant
  instructions the assistant will follow.
- :func:`screen_model_output` -- redaction before anything reaches the
  user, so a secret that slipped into context cannot be echoed back.

**Honest limit**: heuristic pattern matching cannot make prompt
injection impossible, and this does not claim to. It raises the cost of
the obvious attacks and records every detection for audit. The real
structural defences are elsewhere and stronger: tools are permission-
gated per agent, mutating tools require explicit opt-in, and every tool
call is recorded whether it ran or was denied.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.guardrails.redaction import redact
from app.models.enums import GuardrailVerdict

_INJECTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "instruction_override",
        re.compile(
            r"(?i)\b(?:ignore|disregard|forget|override)\b[^.\n]{0,40}\b"
            r"(?:previous|prior|earlier|above|all)\b[^.\n]{0,20}\b"
            r"(?:instruction|prompt|rule|direction|context)s?\b"
        ),
    ),
    (
        "role_reassignment",
        re.compile(r"(?i)\b(?:you\s+are\s+now|act\s+as|pretend\s+to\s+be|from\s+now\s+on\s+you)\b"),
    ),
    (
        "system_prompt_exfiltration",
        re.compile(
            r"(?i)\b(?:reveal|show|print|repeat|output|disclose)\b[^.\n]{0,30}\b"
            r"(?:system\s+prompt|initial\s+instruction|your\s+instruction)s?\b"
        ),
    ),
    (
        "safety_bypass",
        re.compile(r"(?i)\b(?:developer\s+mode|jailbreak|do\s+anything\s+now|dan\s+mode)\b"),
    ),
    (
        "embedded_directive",
        re.compile(r"(?i)\[\[?\s*(?:system|assistant)\s*\]?\]\s*:|<\|\s*(?:im_start|system)\s*\|>"),
    ),
)


@dataclass(frozen=True, slots=True)
class GuardrailResult:
    """What a guardrail decided about one piece of text."""

    verdict: GuardrailVerdict
    text: str
    findings: tuple[str, ...] = ()

    @property
    def is_blocked(self) -> bool:
        """Whether the caller must not proceed with this text."""
        return self.verdict is GuardrailVerdict.BLOCKED


def detect_injection(text: str) -> tuple[str, ...]:
    """Return the names of any injection patterns present in *text*."""
    if not text:
        return ()
    return tuple(name for name, pattern in _INJECTION_PATTERNS if pattern.search(text))


def screen_user_input(text: str) -> GuardrailResult:
    """Screen text a user typed.

    A detection **blocks**: the user is a real party who can be told
    plainly that their message looked like an injection attempt, which
    is better than silently ignoring part of what they asked.
    """
    findings = detect_injection(text)
    if findings:
        return GuardrailResult(verdict=GuardrailVerdict.BLOCKED, text=text, findings=findings)
    return GuardrailResult(verdict=GuardrailVerdict.ALLOWED, text=text)


def screen_retrieved_context(text: str) -> GuardrailResult:
    """Screen a passage retrieved from the knowledge base.

    A detection **neutralises rather than blocks**: dropping the whole
    passage would let anyone who can edit one wiki page delete that
    page from the assistant's knowledge simply by writing an injection
    string into it. The directive is replaced, the rest of the
    legitimate content survives, and the finding is recorded.

    Redaction runs regardless, since indexed documents routinely
    contain credentials that must never reach the model.
    """
    findings = detect_injection(text)
    working = text
    for _name, pattern in _INJECTION_PATTERNS:
        working = pattern.sub("[REMOVED: instruction-like text in retrieved document]", working)

    redaction = redact(working)
    all_findings = (*findings, *redaction.redacted_kinds)
    if not all_findings:
        return GuardrailResult(verdict=GuardrailVerdict.ALLOWED, text=text)
    return GuardrailResult(
        verdict=GuardrailVerdict.REDACTED, text=redaction.text, findings=all_findings
    )


def screen_model_output(text: str) -> GuardrailResult:
    """Screen the model's own reply before it reaches the user."""
    redaction = redact(text)
    if not redaction.was_redacted:
        return GuardrailResult(verdict=GuardrailVerdict.ALLOWED, text=text)
    return GuardrailResult(
        verdict=GuardrailVerdict.REDACTED,
        text=redaction.text,
        findings=redaction.redacted_kinds,
    )


__all__ = [
    "GuardrailResult",
    "detect_injection",
    "screen_model_output",
    "screen_retrieved_context",
    "screen_user_input",
]
