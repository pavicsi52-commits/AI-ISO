"""Plugin Framework metrics.

Per docs/029_Enterprise_Plugin_Framework.md.txt "METRICS": Installed
Plugins, Running Plugins, Execution Time, Failures, Memory Usage, CPU
Usage, Hook Count, Extension Count. Reuses
:mod:`shared_core.metrics.registry` directly (already namespaced,
already registered on the shared default registry) rather than a
second metrics system.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager

from shared_core.metrics.registry import create_counter, create_gauge, create_histogram

plugins_installed_total = create_gauge("plugins_installed_total", "Currently installed plugins.")
plugins_running_total = create_gauge(
    "plugins_running_total", "Currently running (started) plugins."
)
plugin_execution_seconds = create_histogram(
    "plugin_execution_seconds",
    "One plugin operation's duration, in seconds.",
    labels=["plugin_id"],
)
plugin_failures_total = create_counter(
    "plugin_failures_total", "Total plugin operation failures.", labels=["plugin_id"]
)
plugin_memory_usage_mb = create_gauge(
    "plugin_memory_usage_mb", "Process memory usage, in MB, last observed for a plugin operation."
)
plugin_hook_count = create_gauge("plugin_hook_count", "Currently registered hook callbacks.")
plugin_extension_count = create_gauge(
    "plugin_extension_count", "Currently registered extension contributions."
)


def record_installed(count: int) -> None:
    """Set the installed-plugins gauge ("Installed Plugins")."""
    plugins_installed_total.set(count)


def record_running(count: int) -> None:
    """Set the running-plugins gauge ("Running Plugins")."""
    plugins_running_total.set(count)


def record_failure(plugin_id: str) -> None:
    """Increment the failure counter for *plugin_id* ("Failures")."""
    plugin_failures_total.labels(plugin_id=plugin_id).inc()


def record_memory_usage(usage_mb: float) -> None:
    """Set the process memory-usage gauge ("Memory Usage")."""
    plugin_memory_usage_mb.set(usage_mb)


def record_hook_count(count: int) -> None:
    """Set the registered-hooks gauge ("Hook Count")."""
    plugin_hook_count.set(count)


def record_extension_count(count: int) -> None:
    """Set the registered-extensions gauge ("Extension Count")."""
    plugin_extension_count.set(count)


@contextmanager
def measure_execution(plugin_id: str) -> Iterator[None]:
    """Time a plugin operation, observing its duration and any failure ("Execution Time")."""
    start = time.perf_counter()
    try:
        yield
    except Exception:
        record_failure(plugin_id)
        raise
    finally:
        plugin_execution_seconds.labels(plugin_id=plugin_id).observe(time.perf_counter() - start)


__all__ = [
    "measure_execution",
    "plugin_execution_seconds",
    "plugin_extension_count",
    "plugin_failures_total",
    "plugin_hook_count",
    "plugin_memory_usage_mb",
    "plugins_installed_total",
    "plugins_running_total",
    "record_extension_count",
    "record_failure",
    "record_hook_count",
    "record_installed",
    "record_memory_usage",
    "record_running",
]
