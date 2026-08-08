"""Prompt optimization suggestions (docs/061 "PROMPT OPTIMIZATION").

**Every function here returns a *suggestion*, never a mutation.** A
prompt's exact wording is the artefact under version control and
approval in this service; silently rewriting it would bypass the whole
governance workflow the rest of the service exists to enforce. A
suggestion becomes real only when a human accepts it, which creates a
new draft version through the normal review path.

**A genuine gap.** No prompt-optimization machinery exists anywhere
else in this monorepo. The transformations here are deliberately
*mechanical and reversible* -- collapsing whitespace, removing
duplicated instructions, trimming filler phrases -- rather than
model-driven rewrites. A rewrite that changes meaning is worse than no
suggestion at all, and this service cannot call a model to check
(it has no provider credentials by design), so it only proposes
changes whose semantic safety is verifiable by inspection.

``INSTRUCTION_REFINEMENT``, ``FEW_SHOT``, and ``CHAIN`` from docs/061's
own list are reported as **advisory findings** rather than rewrites for
exactly that reason: they identify a structural problem a human should
fix, without guessing at the fix.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.models.enums import OptimizationKind
from app.optimization.tokens import estimate_tokens

DEFAULT_MIN_SAVING_RATIO = 0.05
"""Below this, a suggestion costs more reviewer attention than the
tokens it saves."""

_FILLER_PHRASES: tuple[str, ...] = (
    "please note that",
    "it is important to note that",
    "it should be noted that",
    "as previously mentioned",
    "needless to say",
    "in order to",
    "at this point in time",
    "due to the fact that",
    "for all intents and purposes",
)
"""Phrases that carry no instruction. Each has a shorter equivalent or
is pure padding; none changes what a model is being asked to do."""

_FILLER_REPLACEMENTS: dict[str, str] = {
    "in order to": "to",
    "due to the fact that": "because",
    "at this point in time": "now",
}
"""Where a filler phrase has a genuine shorter equivalent, substitute
it rather than deleting -- dropping "in order to" entirely would break
the sentence."""

_EXCESS_BLANK_LINES = re.compile(r"\n{3,}")
_TRAILING_SPACES = re.compile(r"[ \t]+$", re.MULTILINE)
_REPEATED_SPACES = re.compile(r"  +")

_MIN_MEANINGFUL_LINE = 2
"""A line shorter than this is punctuation or a stray character, not a
duplicated instruction worth reporting."""

_FEW_SHOT_EXAMPLE = re.compile(r"^\s*(example|input|output)\s*[:\-]", re.IGNORECASE | re.MULTILINE)
_CHAIN_STEP = re.compile(
    r"^\s*(step\s*\d+|first|then|next|finally)\b", re.IGNORECASE | re.MULTILINE
)


@dataclass(frozen=True, slots=True)
class Suggestion:
    """One proposed improvement to a prompt body.

    ``suggested_body`` is ``None`` for advisory findings -- the ones
    that identify a problem without guessing at a rewrite.
    """

    kind: OptimizationKind
    rationale: str
    suggested_body: str | None = None
    original_tokens: int = 0
    optimized_tokens: int = 0

    @property
    def token_saving(self) -> int:
        """Tokens saved, never negative."""
        return max(self.original_tokens - self.optimized_tokens, 0)

    @property
    def saving_ratio(self) -> float:
        """Saving as a fraction of the original."""
        if not self.original_tokens:
            return 0.0
        return self.token_saving / self.original_tokens

    @property
    def is_advisory(self) -> bool:
        """Whether this identifies a problem without proposing a rewrite."""
        return self.suggested_body is None


@dataclass(slots=True)
class OptimizationReport:
    """Every suggestion found for one prompt body."""

    original_tokens: int
    suggestions: list[Suggestion] = field(default_factory=list)

    @property
    def best_saving(self) -> int:
        """The largest single token saving on offer."""
        return max((s.token_saving for s in self.suggestions), default=0)


def compress_whitespace(body: str) -> str:
    """Collapse redundant whitespace without changing any wording.

    Purely mechanical and semantically identical: trailing spaces,
    runs of spaces, and three-or-more consecutive newlines all carry no
    instruction. Paragraph breaks (exactly one blank line) are kept,
    because they do affect how a model reads structure.
    """
    collapsed = _TRAILING_SPACES.sub("", body)
    collapsed = _REPEATED_SPACES.sub(" ", collapsed)
    collapsed = _EXCESS_BLANK_LINES.sub("\n\n", collapsed)
    return collapsed.strip()


def remove_filler(body: str) -> str:
    """Drop or shorten filler phrases that carry no instruction."""
    result = body
    for phrase in _FILLER_PHRASES:
        replacement = _FILLER_REPLACEMENTS.get(phrase, "")
        result = re.sub(re.escape(phrase), replacement, result, flags=re.IGNORECASE)
    return compress_whitespace(result)


def find_duplicate_lines(body: str) -> tuple[str, ...]:
    """Non-trivial lines that appear more than once, in first-seen order.

    A duplicated instruction is real waste, but this only *reports*
    duplicates -- deleting one automatically is unsafe, since a repeated
    line is sometimes deliberate emphasis.
    """
    seen: dict[str, int] = {}
    order: list[str] = []
    for raw in body.splitlines():
        line = raw.strip()
        if len(line) < _MIN_MEANINGFUL_LINE:
            continue
        if line not in seen:
            order.append(line)
        seen[line] = seen.get(line, 0) + 1
    return tuple(line for line in order if seen[line] > 1)


def suggest_compression(
    body: str, *, min_saving_ratio: float = DEFAULT_MIN_SAVING_RATIO
) -> Suggestion | None:
    """Suggest a whitespace-and-filler compression, if it saves enough."""
    original_tokens = estimate_tokens(body)
    compressed = remove_filler(compress_whitespace(body))
    optimized_tokens = estimate_tokens(compressed)

    suggestion = Suggestion(
        kind=OptimizationKind.COMPRESSION,
        rationale=(
            "Collapsed redundant whitespace and removed filler phrases. "
            "No instruction wording was changed."
        ),
        suggested_body=compressed,
        original_tokens=original_tokens,
        optimized_tokens=optimized_tokens,
    )
    if compressed == body or suggestion.saving_ratio < min_saving_ratio:
        return None
    return suggestion


def suggest_deduplication(body: str) -> Suggestion | None:
    """Report duplicated instruction lines, advisory only."""
    duplicates = find_duplicate_lines(body)
    if not duplicates:
        return None
    shown = ", ".join(repr(line[:60]) for line in duplicates[:3])
    return Suggestion(
        kind=OptimizationKind.TOKEN,
        rationale=(
            f"{len(duplicates)} instruction line(s) appear more than once ({shown}). "
            "Removing the repeats would save tokens, but a repeated line is "
            "sometimes deliberate emphasis, so this is not rewritten automatically."
        ),
        original_tokens=estimate_tokens(body),
        optimized_tokens=estimate_tokens(body),
    )


def suggest_few_shot_review(body: str, *, max_examples: int = 5) -> Suggestion | None:
    """Flag a prompt carrying more few-shot examples than it likely needs.

    Advisory: which examples to drop depends on what they demonstrate,
    which this service cannot judge without calling a model.
    """
    examples = len(_FEW_SHOT_EXAMPLE.findall(body))
    if examples <= max_examples:
        return None
    return Suggestion(
        kind=OptimizationKind.FEW_SHOT,
        rationale=(
            f"This prompt carries {examples} few-shot examples. Past roughly "
            f"{max_examples}, additional examples usually cost more tokens than "
            "they add accuracy. Review which are still earning their place."
        ),
        original_tokens=estimate_tokens(body),
        optimized_tokens=estimate_tokens(body),
    )


def suggest_chain_review(body: str, *, max_steps: int = 12) -> Suggestion | None:
    """Flag a prompt with a very long inline step chain.

    Advisory: splitting a chain across calls is an architecture change,
    not a text edit.
    """
    steps = len(_CHAIN_STEP.findall(body))
    if steps <= max_steps:
        return None
    return Suggestion(
        kind=OptimizationKind.CHAIN,
        rationale=(
            f"This prompt describes {steps} sequential steps inline. A chain this "
            "long is usually better split across separate calls, which also lets "
            "each step be evaluated on its own."
        ),
        original_tokens=estimate_tokens(body),
        optimized_tokens=estimate_tokens(body),
    )


def suggest_instruction_refinement(body: str, *, max_sentence_words: int = 60) -> Suggestion | None:
    """Flag sentences long enough that an instruction may be getting lost.

    Advisory: rewriting a sentence risks changing what it asks for.
    """
    long_sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", body)
        if len(sentence.split()) > max_sentence_words
    ]
    if not long_sentences:
        return None
    return Suggestion(
        kind=OptimizationKind.INSTRUCTION_REFINEMENT,
        rationale=(
            f"{len(long_sentences)} sentence(s) run over {max_sentence_words} words. "
            "Long compound instructions are easy for a model to partially follow; "
            "splitting them into separate directives usually reads more reliably."
        ),
        original_tokens=estimate_tokens(body),
        optimized_tokens=estimate_tokens(body),
    )


def analyse(body: str, *, min_saving_ratio: float = DEFAULT_MIN_SAVING_RATIO) -> OptimizationReport:
    """Run every optimization check over *body*.

    Returns a report rather than applying anything -- see this module's
    own docstring for why nothing here mutates a prompt.
    """
    report = OptimizationReport(original_tokens=estimate_tokens(body))
    candidates = (
        suggest_compression(body, min_saving_ratio=min_saving_ratio),
        suggest_deduplication(body),
        suggest_few_shot_review(body),
        suggest_chain_review(body),
        suggest_instruction_refinement(body),
    )
    report.suggestions = [candidate for candidate in candidates if candidate is not None]
    return report


__all__ = [
    "DEFAULT_MIN_SAVING_RATIO",
    "OptimizationReport",
    "Suggestion",
    "analyse",
    "compress_whitespace",
    "find_duplicate_lines",
    "remove_filler",
    "suggest_chain_review",
    "suggest_compression",
    "suggest_deduplication",
    "suggest_few_shot_review",
    "suggest_instruction_refinement",
]
