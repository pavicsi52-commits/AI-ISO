"""Message routing.

Per docs/021_Enterprise_Queue_Framework.md.txt "ROUTING": "Configurable
Routing." The broker performs the actual routing decision once a message
is published (topic-pattern matching for a topic exchange, exact-key
matching for direct, headers-matching for headers, none for fanout) --
this module is what builds routing keys consistently and lets calling
code resolve/test a topic pattern client-side (dry runs, tests,
introspection) without needing a live broker round trip.
"""

from __future__ import annotations

from dataclasses import dataclass, field


def build_routing_key(*segments: str) -> str:
    """Join *segments* into a dot-separated AMQP routing key (e.g. ``"asset.discovered.gpu"``).

    Raises:
        ValueError: If no segments are given.
    """
    if not segments:
        raise ValueError("build_routing_key() requires at least one segment.")
    return ".".join(segments)


def topic_matches(pattern: str, routing_key: str) -> bool:
    """Return whether *routing_key* matches an AMQP topic *pattern*.

    Implements the same matching rules as a RabbitMQ topic exchange:
    ``*`` matches exactly one dot-separated word, ``#`` matches zero or
    more words.
    """
    return _match_words(pattern.split("."), routing_key.split("."))


def _match_words(pattern_words: list[str], key_words: list[str]) -> bool:
    if not pattern_words:
        return not key_words
    head, *rest = pattern_words
    if head == "#":
        if not rest:
            return True
        return any(_match_words(rest, key_words[i:]) for i in range(len(key_words) + 1))
    if not key_words:
        return False
    if head not in ("*", key_words[0]):
        return False
    return _match_words(rest, key_words[1:])


@dataclass(frozen=True, slots=True)
class RoutingRule:
    """One topic-pattern -> target-queue mapping."""

    pattern: str
    queue_name: str


@dataclass(slots=True)
class Router:
    """Resolves a routing key to every matching queue name ("Configurable Routing")."""

    _rules: list[RoutingRule] = field(default_factory=list)

    def add_rule(self, pattern: str, queue_name: str) -> None:
        """Register a topic-pattern -> queue routing rule."""
        self._rules.append(RoutingRule(pattern=pattern, queue_name=queue_name))

    def resolve(self, routing_key: str) -> list[str]:
        """Return every queue name whose pattern matches *routing_key*."""
        return [rule.queue_name for rule in self._rules if topic_matches(rule.pattern, routing_key)]

    def clear(self) -> None:
        """Remove every registered rule."""
        self._rules.clear()


__all__ = ["Router", "RoutingRule", "build_routing_key", "topic_matches"]
