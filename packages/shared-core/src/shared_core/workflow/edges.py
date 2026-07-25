"""Workflow edge definitions.

Per docs/028_Enterprise_Workflow_SDK.md.txt "DAG SUPPORT": Directed
Acyclic Graph. An edge connects two nodes; an optional *condition*
expression (evaluated via
:mod:`shared_core.workflow.expressions`) gates whether execution
actually traverses it -- how ``CONDITION``/``SWITCH`` node branching
and ``LOOP`` back-edges are expressed.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EdgeDefinition:
    """A directed edge from one node to another, optionally gated by a condition."""

    from_node_id: str
    to_node_id: str
    condition: str | None = None
    label: str | None = None


__all__ = ["EdgeDefinition"]
