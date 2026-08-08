"""Token estimation (docs/061 "PROMPT OPTIMIZATION": Token
Optimization; "ANALYTICS": Average Tokens).

**This is an estimator, and it says so everywhere it is used.** A real
BPE tokenizer (``tiktoken``) is not a dependency of this platform --
confirmed absent before writing this -- and adding one would tie the
count to one vendor's vocabulary while still being wrong for every
other provider. Anthropic, Google, Llama, and OpenAI all tokenize
differently, so there is no single "true" count to compute anyway.

What this gives instead is a **deterministic, provider-neutral
estimate** good enough for the decisions this service actually makes:
comparing two revisions of the same prompt, ranking optimization
suggestions by saving, and projecting relative cost. It is deliberately
*not* used for billing -- ``prompt_executions.total_tokens`` records
the real count the executing service was charged for, reported back
after the fact by whoever called the model.

The heuristic is a word/punctuation split with a per-character
correction, which tracks real BPE output far better than the widely
repeated "four characters per token" rule: that rule is badly wrong for
code, punctuation-dense text, and non-Latin scripts, all of which
appear in real prompts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_WORD_PATTERN = re.compile(r"\w+|[^\w\s]", re.UNICODE)
"""Words and individual punctuation marks. BPE keeps common words
whole and splits punctuation off, so this matches its shape far more
closely than splitting on whitespace alone."""

_LONG_WORD_THRESHOLD = 6
"""A word longer than this is usually split into multiple BPE tokens.
Six is where common English words stop being single-token in the
vocabularies this was calibrated against."""

_CHARS_PER_SUBTOKEN = 4
"""Within a long word, roughly this many characters per extra piece."""

_NON_ASCII_MULTIPLIER = 2
"""Non-Latin scripts consume markedly more tokens per character in
every Latin-centric BPE vocabulary. Counting them double is crude but
closer than treating them as equivalent to ASCII."""


@dataclass(frozen=True, slots=True)
class TokenEstimate:
    """An estimated token count and the text it was measured from."""

    tokens: int
    characters: int
    words: int

    @property
    def characters_per_token(self) -> float:
        """Observed ratio, for sanity-checking an estimate against reality."""
        return self.characters / self.tokens if self.tokens else 0.0


def estimate_tokens(text: str) -> int:
    """Estimate how many tokens *text* will consume.

    Deterministic: the same string always estimates the same count, so
    a saving computed between two revisions is stable and comparable.
    """
    if not text:
        return 0

    pieces = _WORD_PATTERN.findall(text)
    tokens = 0
    for piece in pieces:
        if len(piece) > _LONG_WORD_THRESHOLD:
            tokens += 1 + (len(piece) - _LONG_WORD_THRESHOLD + _CHARS_PER_SUBTOKEN - 1) // (
                _CHARS_PER_SUBTOKEN
            )
        else:
            tokens += 1
        if not piece.isascii():
            tokens += (len(piece) + _NON_ASCII_MULTIPLIER - 1) // _NON_ASCII_MULTIPLIER

    return max(tokens, 1)


def estimate(text: str) -> TokenEstimate:
    """A full :class:`TokenEstimate` for *text*."""
    return TokenEstimate(
        tokens=estimate_tokens(text),
        characters=len(text),
        words=len(_WORD_PATTERN.findall(text)),
    )


def estimate_cost_usd(tokens: int, *, usd_per_1k_tokens: float) -> float:
    """Project a cost from an estimated token count.

    Raises:
        ValueError: If *usd_per_1k_tokens* is negative.
    """
    if usd_per_1k_tokens < 0:
        raise ValueError(f"usd_per_1k_tokens cannot be negative, got {usd_per_1k_tokens!r}.")
    return (tokens / 1_000.0) * usd_per_1k_tokens


__all__ = [
    "TokenEstimate",
    "estimate",
    "estimate_cost_usd",
    "estimate_tokens",
]
