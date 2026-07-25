"""Development-only configuration hot-reload watcher.

Per docs/013_Configuration_Framework.md.txt "HOT RELOAD": automatically
reload configuration when its source files change; development only,
always disabled in production. Polls file mtimes rather than depending on
a native filesystem-events library, keeping the framework dependency-free
and portable (see AI_MEMORY.md's ``DistributedLock``/``lupa`` note for why
native dependencies are avoided on this platform wherever a pure-Python
alternative exists).
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable, Sequence
from pathlib import Path

from shared_core.config.cache import reload_settings
from shared_core.config.constants import ConfigConstants
from shared_core.config.environment import Environment
from shared_core.config.loader import env_files_for
from shared_core.logging import get_logger

logger = get_logger(__name__)


class ConfigWatcher:
    """Polls configuration files for changes and reloads settings when they change.

    Inert (``start()`` is a no-op) unless ``environment.allows_hot_reload``
    is ``True`` -- most importantly, this makes it always inert in
    production regardless of how it's wired up.
    """

    def __init__(
        self,
        environment: Environment,
        *,
        files: Sequence[Path] | None = None,
        poll_interval_seconds: float = ConfigConstants.DEFAULT_WATCH_POLL_INTERVAL_SECONDS,
        on_reload: Callable[[], None] | None = None,
    ) -> None:
        self._environment = environment
        self._files = (
            list(files)
            if files is not None
            else [Path(name) for name in env_files_for(environment)]
        )
        self._poll_interval_seconds = poll_interval_seconds
        self._on_reload = on_reload
        self._task: asyncio.Task[None] | None = None
        self._mtimes: dict[Path, float] = {}

    @property
    def is_running(self) -> bool:
        """Whether the background polling task is currently active."""
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        """Start watching, unless hot reload is disallowed for this environment."""
        if not self._environment.allows_hot_reload:
            logger.info("config.watch.skipped", extra={"reason": "hot_reload_disabled"})
            return
        if self.is_running:
            return
        self._mtimes = self._snapshot()
        self._task = asyncio.create_task(self._run())
        logger.info("config.watch.started", extra={"files": [str(f) for f in self._files]})

    async def stop(self) -> None:
        """Stop watching and wait for the background task to finish."""
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None
        logger.info("config.watch.stopped")

    def _snapshot(self) -> dict[Path, float]:
        snapshot: dict[Path, float] = {}
        for path in self._files:
            if path.is_file():
                snapshot[path] = path.stat().st_mtime
        return snapshot

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self._poll_interval_seconds)
            current = self._snapshot()
            if current != self._mtimes:
                logger.info("config.watch.changed")
                reload_settings()
                if self._on_reload is not None:
                    self._on_reload()
                self._mtimes = current
