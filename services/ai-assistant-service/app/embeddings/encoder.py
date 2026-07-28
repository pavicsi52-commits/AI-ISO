"""Embedding generation ("RAG": Embeddings).

Two real strategies, chosen by provider:

- **Hosted/self-hosted providers** (OpenAI, Azure, Ollama, vLLM,
  OpenRouter, local OpenAI-compatible endpoints) call the provider's
  own documented embeddings REST API over ``httpx`` -- see
  :mod:`app.clients.embedding_client`.
- **``builtin``** uses :class:`HashingEncoder` below, which needs no
  network, no credential, and no model download.

:class:`HashingEncoder` is **feature hashing** (the "hashing trick"), a
long-established real technique -- not a placeholder. It projects token
counts into a fixed-width vector via a stable hash, then L2-normalises
so cosine similarity behaves. What it genuinely gives you: deterministic
vectors, exact-term overlap, and a fully working RAG pipeline offline.
What it genuinely does **not** give you: semantics. "server is down"
and "host is unreachable" share no tokens and will score as unrelated,
where a trained embedding model would place them close together.

That limit is stated plainly rather than papered over: the default for
any deployment that cares about answer quality is a real embedding
model via a provider, and ``local`` exists so the pipeline is testable
and runnable with zero external dependencies.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter

_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+")

BUILTIN_PROVIDER = "builtin"
"""Sentinel selecting this in-process encoder instead of a network call.

Deliberately **not** ``"local"``. ``ModelProvider.LOCAL`` is already
``"local"`` and means something entirely different -- a self-hosted
OpenAI-compatible endpoint. Sharing the string made the two
indistinguishable in
:func:`app.clients.registry.build_embedding_client`, so an operator who
pointed ``default_embedding_provider`` at their own embedding server
silently got this offline lexical encoder instead: no error, no log,
just a quiet collapse from semantic to keyword retrieval. The two
concepts now have two names.
"""

BUILTIN_MODEL = "builtin-hashing"
"""Recorded as the model name for vectors this encoder produced.

Stored on every embedding row so a corpus indexed offline is
distinguishable from one indexed by a real provider -- they are not
comparable, and mixing them in one index would silently degrade
ranking.
"""


def tokenize(text: str) -> list[str]:
    """Lowercased alphanumeric tokens.

    Deliberately keeps digits and underscores: hostnames, error codes,
    and identifiers are exactly what lexical matching is for.
    """
    return [match.group(0).lower() for match in _TOKEN_PATTERN.finditer(text)]


class HashingEncoder:
    """Deterministic feature-hashing encoder. See the module docstring
    for what this does and does not provide.
    """

    def __init__(self, dimensions: int) -> None:
        """Build an encoder producing vectors of *dimensions* width.

        Raises:
            ValueError: If *dimensions* is not positive.
        """
        if dimensions <= 0:
            raise ValueError(f"dimensions must be positive, got {dimensions!r}.")
        self._dimensions = dimensions

    @property
    def dimensions(self) -> int:
        """The width of every vector this encoder produces."""
        return self._dimensions

    def _bucket(self, token: str) -> tuple[int, float]:
        """Map *token* to a bucket index and a stable +/-1 sign.

        The sign halves the bias that pure additive hashing introduces
        when unrelated tokens collide -- the standard signed variant of
        the hashing trick.
        """
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:8], "big") % self._dimensions
        sign = 1.0 if digest[8] & 1 else -1.0
        return index, sign

    def encode(self, text: str) -> list[float]:
        """Return an L2-normalised vector for *text*.

        An empty or token-free input returns an all-zero vector rather
        than raising: an empty document is a legitimate, if useless,
        thing to index, and a zero vector simply never matches.
        """
        vector = [0.0] * self._dimensions
        counts = Counter(tokenize(text))
        if not counts:
            return vector

        for token, count in counts.items():
            index, sign = self._bucket(token)
            # Sublinear term-frequency damping: a term repeated 100
            # times is more relevant than one repeated once, but not
            # 100x more.
            vector[index] += sign * (1.0 + math.log(count))

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0.0:
            return vector
        return [value / norm for value in vector]


__all__ = ["BUILTIN_MODEL", "BUILTIN_PROVIDER", "HashingEncoder", "tokenize"]
