"""Graph entity shapes: what a node and a relationship are here.

These are the boundary types between Cypher records and everything
above them. Keeping them explicit means a traversal result is a
``GraphNode``, not a dict whose keys each caller guesses at.

**``key`` is the identity, not Neo4j's internal id.** Internal ids are
reused after deletion and are explicitly not stable across a restore,
so nothing outside this module ever sees one. ``key`` is the stable
business identifier the owning source service assigns, and it is what
joins a node to its :class:`~app.models.graph_metadata.GraphMetadata`
row in PostgreSQL.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator
from shared_core.exceptions.validation import ValidationError

from app.cypher.builder import validate_label, validate_relationship_type
from app.models.enums import NodeType, RelationshipType

_RESERVED_PROPERTIES: frozenset[str] = frozenset(
    {"key", "organization_id", "project_id", "node_type", "created_at", "updated_at", "source"}
)
"""Property names this service owns on every node.

A caller-supplied property with one of these names would overwrite the
identity or tenant of the node it is attached to, so they are refused
rather than merged. That is a real escalation path: a payload setting
``organization_id`` moves a node into another tenant graph.
"""


def _clean_properties(properties: dict[str, Any] | None) -> dict[str, Any]:
    """Strip reserved names from caller-supplied properties.

    Raises:
        ValidationError: If a reserved name is present. Silently
            dropping it would leave the caller believing it was stored.
    """
    values = properties or {}
    reserved = sorted(set(values) & _RESERVED_PROPERTIES)
    if reserved:
        raise ValidationError(
            f"These property names are managed by the graph and cannot be set "
            f"directly: {', '.join(reserved)}."
        )
    return dict(values)


class NodeInput(BaseModel):
    """A node as a caller writes it."""

    key: str = Field(min_length=1, max_length=255)
    node_type: NodeType
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2_000)
    properties: dict[str, Any] = Field(default_factory=dict)
    project_id: str | None = Field(default=None, max_length=64)
    source: str | None = Field(default=None, max_length=64)

    @field_validator("properties")
    @classmethod
    def _reject_reserved(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _clean_properties(value)


class RelationshipInput(BaseModel):
    """A relationship as a caller writes it."""

    from_key: str = Field(min_length=1, max_length=255)
    to_key: str = Field(min_length=1, max_length=255)
    relationship_type: RelationshipType
    properties: dict[str, Any] = Field(default_factory=dict)
    weight: float = Field(default=1.0, ge=0.0)
    """How strongly the dependency propagates, 0.0-1.0+.

    Used by risk propagation and dependency scoring. A default of 1.0
    means "fully propagating" -- the safe assumption for an edge nobody
    has characterised, because under-stating propagation hides risk.
    """

    @field_validator("properties")
    @classmethod
    def _reject_reserved(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _clean_properties(value)

    @model_validator(mode="after")
    def _reject_self_loop(self) -> RelationshipInput:
        """Refuse an edge from a node to itself.

        Enforced on the **model** rather than in a separate validator
        function, so every construction path is covered -- the importer
        and the sync mappers build these directly, and a self-loop that
        only failed later at write time would abort a whole batch
        instead of being one rejected row.

        A self-loop makes every dependency traversal cyclic and every
        blast radius infinite.
        """
        if self.from_key == self.to_key:
            raise ValueError(
                f"A node cannot relate to itself ({self.from_key!r}); a self-loop "
                "makes dependency traversal cyclic."
            )
        return self


@dataclass(slots=True)
class GraphNode:
    """One node, as read back from the graph."""

    key: str
    node_type: str
    name: str
    organization_id: str
    description: str | None = None
    project_id: str | None = None
    source: str | None = None
    properties: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> GraphNode:
        """Build a node from a Cypher record's node properties."""
        properties = dict(record or {})
        return cls(
            key=str(properties.pop("key", "")),
            node_type=str(properties.pop("node_type", NodeType.CUSTOM_NODE)),
            name=str(properties.pop("name", "")),
            organization_id=str(properties.pop("organization_id", "")),
            description=_optional_str(properties.pop("description", None)),
            project_id=_optional_str(properties.pop("project_id", None)),
            source=_optional_str(properties.pop("source", None)),
            created_at=_as_datetime(properties.pop("created_at", None)),
            updated_at=_as_datetime(properties.pop("updated_at", None)),
            properties=properties,
        )

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable form for an API response."""
        return {
            "key": self.key,
            "node_type": self.node_type,
            "name": self.name,
            "description": self.description,
            "organization_id": self.organization_id,
            "project_id": self.project_id,
            "source": self.source,
            "properties": self.properties,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


@dataclass(slots=True)
class GraphRelationship:
    """One relationship, as read back from the graph."""

    from_key: str
    to_key: str
    relationship_type: str
    weight: float = 1.0
    properties: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None

    @property
    def relationship_key(self) -> str:
        """A stable identifier for this edge.

        Derived from its endpoints and type rather than stored, because
        Neo4j relationship ids are internal and unstable across a
        restore -- the same reason nodes are keyed by business
        identifier. Deriving it means an edge deleted and recreated by a
        sync keeps the same identity in the change log.
        """
        return f"{self.from_key}|{self.relationship_type}|{self.to_key}"

    @classmethod
    def from_record(
        cls, record: dict[str, Any], *, from_key: str, to_key: str, relationship_type: str
    ) -> GraphRelationship:
        """Build a relationship from a Cypher record."""
        properties = dict(record or {})
        weight = properties.pop("weight", 1.0)
        return cls(
            from_key=from_key,
            to_key=to_key,
            relationship_type=relationship_type,
            weight=float(weight) if isinstance(weight, int | float) else 1.0,
            created_at=_as_datetime(properties.pop("created_at", None)),
            properties=properties,
        )

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable form for an API response."""
        return {
            "relationship_key": self.relationship_key,
            "from_key": self.from_key,
            "to_key": self.to_key,
            "relationship_type": self.relationship_type,
            "weight": self.weight,
            "properties": self.properties,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


@dataclass(slots=True)
class Subgraph:
    """A set of nodes and the relationships between them."""

    nodes: list[GraphNode] = field(default_factory=list)
    relationships: list[GraphRelationship] = field(default_factory=list)
    truncated: bool = False
    root_key: str | None = None

    @property
    def node_count(self) -> int:
        """How many nodes the subgraph holds."""
        return len(self.nodes)

    def node_keys(self) -> set[str]:
        """Every node key present."""
        return {node.key for node in self.nodes}

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable form for an API response."""
        return {
            "root_key": self.root_key,
            "nodes": [node.as_dict() for node in self.nodes],
            "relationships": [edge.as_dict() for edge in self.relationships],
            "node_count": len(self.nodes),
            "relationship_count": len(self.relationships),
            "truncated": self.truncated,
        }


def validate_node_input(node: NodeInput) -> NodeInput:
    """Confirm a node's label is one this service will write.

    Raises:
        ValidationError: If the node type is unknown.
    """
    validate_label(node.node_type)
    return node


def validate_relationship_input(relationship: RelationshipInput) -> RelationshipInput:
    """Confirm a relationship's type is one this service will write.

    The self-loop rule lives on :class:`RelationshipInput` itself rather
    than here, so it holds for every construction path rather than only
    the ones that remember to call this.

    Raises:
        ValidationError: If the relationship type is not a known type.
    """
    validate_relationship_type(relationship.relationship_type)
    return relationship


def _optional_str(value: Any) -> str | None:
    """Coerce to ``str``, keeping ``None`` as ``None``."""
    return None if value is None else str(value)


def _as_datetime(value: Any) -> datetime | None:
    """Coerce a Neo4j temporal or ISO string into a ``datetime``.

    The driver returns its own ``DateTime`` type, which is not a
    ``datetime`` -- handing it straight to Pydantic produces a confusing
    error a long way from here.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    to_native = getattr(value, "to_native", None)
    if callable(to_native):
        native = to_native()
        return native if isinstance(native, datetime) else None
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def utcnow() -> datetime:
    """The current moment, timezone-aware."""
    return datetime.now(UTC)


__all__ = [
    "GraphNode",
    "GraphRelationship",
    "NodeInput",
    "RelationshipInput",
    "Subgraph",
    "utcnow",
    "validate_node_input",
    "validate_relationship_input",
]
