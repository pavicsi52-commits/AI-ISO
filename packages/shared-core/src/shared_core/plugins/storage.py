"""Plugin-scoped storage.

Per docs/029_Enterprise_Plugin_Framework.md.txt "PERMISSIONS": Storage.
Wraps :class:`shared_core.storage.wrapper.StorageWrapper` (Prompt 012's
MinIO wrapper), scoping every key under a ``plugins/<plugin_id>/``
prefix so one plugin's storage can never collide with -- or read --
another's, and enforcing ``PluginPermission.STORAGE`` via the plugin's
own sandbox before every operation.
"""

from __future__ import annotations

from shared_core.plugins.permissions import PluginPermission
from shared_core.plugins.sandbox import PluginSandbox
from shared_core.storage.wrapper import StorageWrapper

_PREFIX = "plugins"


class PluginStorage:
    """One plugin's sandboxed, namespaced view over object storage."""

    def __init__(
        self, plugin_id: str, wrapper: StorageWrapper, *, sandbox: PluginSandbox | None = None
    ) -> None:
        self.plugin_id = plugin_id
        self._wrapper = wrapper
        self._sandbox = sandbox

    def scoped_key(self, key: str) -> str:
        """The fully-namespaced storage key for this plugin's *key*."""
        return f"{_PREFIX}/{self.plugin_id}/{key}"

    def _check_permission(self) -> None:
        if self._sandbox is not None:
            self._sandbox.check_permission(PluginPermission.STORAGE)

    async def upload(self, bucket: str, key: str, data: bytes, content_type: str) -> str:
        """Upload *data* under this plugin's namespaced *key*.

        Raises:
            SandboxViolationError: If a sandbox is configured and doesn't grant ``STORAGE``.
        """
        self._check_permission()
        return await self._wrapper.upload(bucket, self.scoped_key(key), data, content_type)

    async def download(self, bucket: str, key: str) -> bytes:
        """Download this plugin's namespaced *key*.

        Raises:
            SandboxViolationError: If a sandbox is configured and doesn't grant ``STORAGE``.
        """
        self._check_permission()
        return await self._wrapper.download(bucket, self.scoped_key(key))

    async def delete(self, bucket: str, key: str) -> None:
        """Delete this plugin's namespaced *key*.

        Raises:
            SandboxViolationError: If a sandbox is configured and doesn't grant ``STORAGE``.
        """
        self._check_permission()
        await self._wrapper.delete(bucket, self.scoped_key(key))

    async def exists(self, bucket: str, key: str) -> bool:
        """Whether this plugin's namespaced *key* exists.

        Raises:
            SandboxViolationError: If a sandbox is configured and doesn't grant ``STORAGE``.
        """
        self._check_permission()
        return await self._wrapper.exists(bucket, self.scoped_key(key))


__all__ = ["PluginStorage"]
