"""AI extension points.

Per docs/029_Enterprise_Plugin_Framework.md.txt "AI EXTENSIONS": Custom
Models, Prompt Templates, Agents, Decision Engines, Embeddings,
Inference Providers. A
:class:`~shared_core.plugins.extensions.NamespacedExtensions` scoped to
the ``"ai"`` namespace -- lets a plugin contribute a model/prompt/agent
implementation that a host service registers into its own AI framework
integration; this module only tracks *what* a plugin contributed, not
how any AI framework itself runs inference.
"""

from __future__ import annotations

from shared_core.plugins.extensions import ExtensionRegistry, NamespacedExtensions


class AiExtensions(NamespacedExtensions):
    """AI contribution categories: custom models, prompt templates,
    agents, decision engines, embeddings, inference providers.
    """

    def __init__(self, registry: ExtensionRegistry) -> None:
        super().__init__(registry, namespace="ai")


__all__ = ["AiExtensions"]
