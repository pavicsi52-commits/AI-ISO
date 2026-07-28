"""Document chunking ("RAG": Chunking).

Splits a document into overlapping passages sized for retrieval. Two
properties matter and are both deliberate:

- **Boundary-aware.** A naive fixed-width cut lands mid-sentence and
  mid-word, which measurably degrades both embedding quality and the
  readability of a citation. This splitter prefers to break at a
  paragraph, then a sentence, then a word, and only cuts mid-token when
  a single token genuinely exceeds the window.
- **Overlapping.** Consecutive chunks share ``overlap`` characters so a
  fact spanning a boundary survives in at least one whole chunk rather
  than being severed by it.
"""

from __future__ import annotations

from dataclasses import dataclass

_PARAGRAPH_BREAK = "\n\n"
_SENTENCE_ENDINGS = (". ", "! ", "? ", ".\n", "!\n", "?\n")


@dataclass(frozen=True, slots=True)
class Chunk:
    """One produced passage and where it sat in the source."""

    sequence: int
    content: str
    start: int
    end: int

    @property
    def token_estimate(self) -> int:
        """A rough token count for budgeting context windows.

        Deliberately an *estimate*: real tokenization is
        model-specific, and pulling in a tokenizer per provider would
        add a dependency for a number only used to decide how much
        context still fits. Four characters per token is the widely
        used approximation for English prose.
        """
        return max(1, len(self.content) // 4)


def _best_break(text: str, window_end: int) -> int:
    """Find the nicest place to cut at or before *window_end*.

    Searches only the last third of the window: a break far earlier
    would waste most of the chunk, so past that point an uglier cut is
    the better trade.
    """
    floor = window_end - (window_end // 3)

    paragraph = text.rfind(_PARAGRAPH_BREAK, floor, window_end)
    if paragraph != -1:
        return paragraph + len(_PARAGRAPH_BREAK)

    best_sentence = -1
    for ending in _SENTENCE_ENDINGS:
        found = text.rfind(ending, floor, window_end)
        if found > best_sentence:
            best_sentence = found + len(ending)
    if best_sentence != -1:
        return best_sentence

    space = text.rfind(" ", floor, window_end)
    if space != -1:
        return space + 1

    return window_end


def chunk_text(text: str, *, chunk_size: int, overlap: int) -> list[Chunk]:
    """Split *text* into overlapping, boundary-aware chunks.

    Raises:
        ValueError: If *chunk_size* is not positive, or *overlap* is
            negative or not smaller than *chunk_size* (an overlap at
            least as large as the window can never advance and would
            loop forever).
    """
    if chunk_size <= 0:
        raise ValueError(f"chunk_size must be positive, got {chunk_size!r}.")
    if overlap < 0:
        raise ValueError(f"overlap must not be negative, got {overlap!r}.")
    if overlap >= chunk_size:
        raise ValueError(
            f"overlap ({overlap}) must be smaller than chunk_size ({chunk_size}); "
            "otherwise chunking can never advance."
        )

    stripped = text.strip()
    if not stripped:
        return []

    chunks: list[Chunk] = []
    position = 0
    sequence = 0
    length = len(stripped)

    while position < length:
        window_end = min(position + chunk_size, length)
        cut = window_end if window_end >= length else _best_break(stripped, window_end)
        # A break search can return the window start when the whole
        # window is one unbroken token; fall back to a hard cut so the
        # loop always advances.
        if cut <= position:
            cut = window_end

        content = stripped[position:cut].strip()
        if content:
            chunks.append(Chunk(sequence=sequence, content=content, start=position, end=cut))
            sequence += 1

        if cut >= length:
            break
        position = max(cut - overlap, position + 1)

    return chunks


__all__ = ["Chunk", "chunk_text"]
