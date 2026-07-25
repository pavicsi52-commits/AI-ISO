"""UI extension points.

Per docs/029_Enterprise_Plugin_Framework.md.txt "UI EXTENSIONS": Menus,
Pages, Widgets, Dashboards, Tables, Forms, Charts, Settings, Navigation.
A :class:`~shared_core.plugins.extensions.NamespacedExtensions` scoped
to the ``"ui"`` namespace -- no new mechanism, just a typed, documented
entry point for this specific extension category.
"""

from __future__ import annotations

from shared_core.plugins.extensions import ExtensionRegistry, NamespacedExtensions


class UiExtensions(NamespacedExtensions):
    """UI contribution categories: menus, pages, widgets, dashboards,
    tables, forms, charts, settings, navigation.
    """

    def __init__(self, registry: ExtensionRegistry) -> None:
        super().__init__(registry, namespace="ui")


__all__ = ["UiExtensions"]
