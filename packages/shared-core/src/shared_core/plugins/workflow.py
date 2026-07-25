"""Workflow SDK extension points.

Per docs/029_Enterprise_Plugin_Framework.md.txt "WORKFLOW EXTENSIONS":
Tasks, Conditions, Actions, Expressions, Templates, Nodes, Variables.
A :class:`~shared_core.plugins.extensions.NamespacedExtensions` scoped
to the ``"workflow"`` namespace -- lets a plugin contribute node
handlers, condition functions, etc. that a host service then registers
into its own :class:`shared_core.workflow.executor.NodeHandlerRegistry`
(Prompt 028); this module only tracks *what* a plugin contributed, not
how the Workflow SDK itself executes it.
"""

from __future__ import annotations

from shared_core.plugins.extensions import ExtensionRegistry, NamespacedExtensions


class WorkflowExtensions(NamespacedExtensions):
    """Workflow contribution categories: tasks, conditions, actions,
    expressions, templates, nodes, variables.
    """

    def __init__(self, registry: ExtensionRegistry) -> None:
        super().__init__(registry, namespace="workflow")


__all__ = ["WorkflowExtensions"]
