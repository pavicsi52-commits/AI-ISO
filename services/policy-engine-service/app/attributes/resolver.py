"""Resolving an attribute path against an evaluation request.

A condition names an attribute like ``subject.roles`` or
``context.ip_address``; this turns that into a value. The grammar is
deliberately tiny -- a source, then dotted keys, with numeric segments
indexing into lists -- because an attribute path is caller-authored and
runs on the authorization path.

**A missing attribute is not ``None``.** It resolves to
:data:`~app.conditions.operators._MISSING`, which is what lets ``exists``
answer correctly for an attribute explicitly set to null. Collapsing the
two would make "this field is absent" and "this field is null"
indistinguishable, and policies are written against exactly that
distinction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from shared_core.exceptions.validation import ValidationError

from app.conditions.operators import _MISSING
from app.models.enums import AttributeSource

MAX_PATH_DEPTH = 8
"""How deep an attribute path may go.

Bounded because the path is caller-authored and each segment is a
dictionary lookup on data this service did not construct. Eight is far
past anything a real policy needs and far short of anything that costs.
"""

_SEGMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$|^\d+$")
"""What one path segment may look like: an identifier or a list index."""


@dataclass(slots=True)
class EvaluationContext:
    """Everything one decision is allowed to see.

    The four ABAC dimensions plus the ambient context, each a plain
    mapping. Nothing here is fetched lazily: a policy decision that
    reaches out mid-evaluation is a decision whose latency and failure
    modes depend on a third party, and this service sits in front of
    every protected operation on the platform.
    """

    subject: dict[str, Any] = field(default_factory=dict)
    resource: dict[str, Any] = field(default_factory=dict)
    action: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)
    environment: dict[str, Any] = field(default_factory=dict)
    organization: dict[str, Any] = field(default_factory=dict)
    project: dict[str, Any] = field(default_factory=dict)
    custom: dict[str, Any] = field(default_factory=dict)

    def source(self, source: AttributeSource) -> dict[str, Any]:
        """The mapping one source refers to."""
        return {
            AttributeSource.SUBJECT: self.subject,
            AttributeSource.RESOURCE: self.resource,
            AttributeSource.ACTION: self.action,
            AttributeSource.CONTEXT: self.context,
            AttributeSource.ENVIRONMENT: self.environment,
            AttributeSource.ORGANIZATION: self.organization,
            AttributeSource.PROJECT: self.project,
            AttributeSource.CUSTOM: self.custom,
        }[source]

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable form, for storing alongside a decision."""
        return {
            "subject": self.subject,
            "resource": self.resource,
            "action": self.action,
            "context": self.context,
            "environment": self.environment,
            "organization": self.organization,
            "project": self.project,
            "custom": self.custom,
        }


def validate_path(path: str) -> list[str]:
    """Split and validate a dotted attribute path.

    Raises:
        ValidationError: If the path is empty, too deep, or holds a
            segment that is not a plain identifier or list index.
            Refused at authoring time so a policy carrying an unusable
            path never reaches a decision.
    """
    cleaned = path.strip()
    if not cleaned:
        raise ValidationError("An attribute path cannot be empty.")
    segments = cleaned.split(".")
    if len(segments) > MAX_PATH_DEPTH:
        raise ValidationError(
            f"An attribute path may be at most {MAX_PATH_DEPTH} segments deep, "
            f"got {len(segments)} in {path!r}."
        )
    for segment in segments:
        if not _SEGMENT.match(segment):
            raise ValidationError(
                f"{segment!r} is not a valid attribute path segment in {path!r}. "
                "Segments must be identifiers or list indices."
            )
    return segments


def resolve(context: EvaluationContext, source: AttributeSource, path: str) -> Any:
    """Read one attribute, or :data:`_MISSING` if it is not there.

    Never raises for a path that does not lead anywhere -- walking off
    the end of the data is the normal case for an optional attribute,
    and an exception there would turn every policy referencing an
    optional field into a failed decision.

    Raises:
        ValidationError: Only if the path itself is malformed.
    """
    current: Any = context.source(source)
    for segment in validate_path(path):
        if isinstance(current, dict):
            if segment not in current:
                return _MISSING
            current = current[segment]
        elif isinstance(current, list | tuple):
            if not segment.isdigit():
                return _MISSING
            index = int(segment)
            if index >= len(current):
                return _MISSING
            current = current[index]
        else:
            return _MISSING
    return current


def is_missing(value: Any) -> bool:
    """Whether a resolved value means "the attribute was not present"."""
    return value is _MISSING


__all__ = [
    "MAX_PATH_DEPTH",
    "EvaluationContext",
    "is_missing",
    "resolve",
    "validate_path",
]
