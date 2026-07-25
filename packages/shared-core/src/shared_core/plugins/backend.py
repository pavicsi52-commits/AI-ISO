"""Backend extension points.

Per docs/029_Enterprise_Plugin_Framework.md.txt "BACKEND EXTENSIONS":
REST Endpoints, Background Workers, Scheduled Jobs, Queue Consumers,
Services, Middleware, Decorators, Validators. A
:class:`~shared_core.plugins.extensions.NamespacedExtensions` scoped to
the ``"backend"`` namespace -- no new mechanism, just a typed,
documented entry point for this specific extension category.
"""

from __future__ import annotations

from shared_core.plugins.extensions import ExtensionRegistry, NamespacedExtensions


class BackendExtensions(NamespacedExtensions):
    """Backend contribution categories: REST endpoints, background
    workers, scheduled jobs, queue consumers, services, middleware,
    decorators, validators.
    """

    def __init__(self, registry: ExtensionRegistry) -> None:
        super().__init__(registry, namespace="backend")


__all__ = ["BackendExtensions"]
