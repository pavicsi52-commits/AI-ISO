"""Workflow definition registry.

Per docs/028_Enterprise_Workflow_SDK.md.txt "WORKFLOW PRINCIPLES":
"Every workflow is versioned." The in-process, authoritative store of
every :class:`~shared_core.workflow.definition.WorkflowDefinition` a
service knows about, keyed by workflow id *and* version so multiple
versions of the same workflow can coexist -- the same "purely
in-process" pattern as :class:`shared_core.scheduler.registry.JobRegistry`.
Persistence across restarts is a concern for whatever repository layer
wraps this registry in a running service.
"""

from __future__ import annotations

from shared_core.workflow.definition import WorkflowDefinition
from shared_core.workflow.exceptions import WorkflowNotFoundError


class WorkflowRegistry:
    """The authoritative in-process store of registered workflow definitions."""

    def __init__(self) -> None:
        self._definitions: dict[str, dict[str, WorkflowDefinition]] = {}
        self._latest_version: dict[str, str] = {}

    def register(self, definition: WorkflowDefinition) -> None:
        """Add or replace *definition* ("Workflow Created"/"Workflow Updated").

        Also becomes the workflow id's latest version, superseding
        whichever version was previously latest.
        """
        versions = self._definitions.setdefault(definition.workflow_id, {})
        versions[definition.version] = definition
        self._latest_version[definition.workflow_id] = definition.version

    def unregister(self, workflow_id: str, *, version: str | None = None) -> None:
        """Remove one version of *workflow_id*, or the whole workflow if *version* is ``None``.

        A no-op if the workflow (or version) isn't registered.
        """
        if version is None:
            self._definitions.pop(workflow_id, None)
            self._latest_version.pop(workflow_id, None)
            return
        versions = self._definitions.get(workflow_id)
        if versions is None:
            return
        versions.pop(version, None)
        if not versions:
            self._definitions.pop(workflow_id, None)
            self._latest_version.pop(workflow_id, None)
        elif self._latest_version.get(workflow_id) == version:
            self._latest_version[workflow_id] = next(reversed(versions))

    def get(self, workflow_id: str, *, version: str | None = None) -> WorkflowDefinition:
        """Look up a workflow definition, defaulting to its latest registered version.

        Raises:
            WorkflowNotFoundError: If *workflow_id* (or that specific
                *version*) is not registered.
        """
        versions = self._definitions.get(workflow_id)
        if not versions:
            raise WorkflowNotFoundError(f"Workflow {workflow_id!r} is not registered.")
        resolved_version = version if version is not None else self._latest_version[workflow_id]
        try:
            return versions[resolved_version]
        except KeyError as exc:
            raise WorkflowNotFoundError(
                f"Workflow {workflow_id!r} has no version {resolved_version!r} registered."
            ) from exc

    def has(self, workflow_id: str, *, version: str | None = None) -> bool:
        """Whether *workflow_id* (optionally at *version*) is registered."""
        versions = self._definitions.get(workflow_id)
        if versions is None:
            return False
        return version is None or version in versions

    def list_workflow_ids(self) -> list[str]:
        """Every currently registered workflow id."""
        return list(self._definitions)

    def list_versions(self, workflow_id: str) -> list[str]:
        """Every registered version of *workflow_id*, oldest-registered first."""
        return list(self._definitions.get(workflow_id, {}))


__all__ = ["WorkflowRegistry"]
