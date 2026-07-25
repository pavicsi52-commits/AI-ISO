"""System resource monitoring.

Per docs/023_Enterprise_Monitoring_Framework.md.txt "RESOURCE
MONITORING": CPU, Memory, Disk, Filesystem, Processes, Network,
Bandwidth, Open Files. ("GPU (Future)" is explicitly out of scope.)
"""

from __future__ import annotations

from dataclasses import dataclass

import psutil


@dataclass(frozen=True, slots=True)
class DiskUsage:
    """Usage for one mounted filesystem."""

    mount_point: str
    total_bytes: int
    used_bytes: int
    free_bytes: int
    percent: float


@dataclass(frozen=True, slots=True)
class NetworkUsage:
    """Host-wide network interface counters ("Network" / "Bandwidth")."""

    bytes_sent: int
    bytes_received: int
    packets_sent: int
    packets_received: int
    errors_in: int
    errors_out: int


@dataclass(frozen=True, slots=True)
class ResourceSnapshot:
    """A point-in-time snapshot of the host's own resource usage."""

    cpu_percent: float
    cpu_count: int
    memory_total_bytes: int
    memory_used_bytes: int
    memory_percent: float
    disks: tuple[DiskUsage, ...]
    network: NetworkUsage
    process_count: int


def _disk_usage(mount_point: str) -> DiskUsage:
    try:
        usage = psutil.disk_usage(mount_point)
    except OSError:
        return DiskUsage(
            mount_point=mount_point, total_bytes=0, used_bytes=0, free_bytes=0, percent=0.0
        )
    return DiskUsage(
        mount_point=mount_point,
        total_bytes=usage.total,
        used_bytes=usage.used,
        free_bytes=usage.free,
        percent=usage.percent,
    )


def capture_resource_snapshot() -> ResourceSnapshot:
    """Capture host-wide CPU/memory/disk/network/process state."""
    memory = psutil.virtual_memory()
    disks = tuple(
        _disk_usage(partition.mountpoint) for partition in psutil.disk_partitions(all=False)
    )
    net = psutil.net_io_counters()
    return ResourceSnapshot(
        cpu_percent=psutil.cpu_percent(interval=None),
        cpu_count=psutil.cpu_count() or 0,
        memory_total_bytes=memory.total,
        memory_used_bytes=memory.used,
        memory_percent=memory.percent,
        disks=disks,
        network=NetworkUsage(
            bytes_sent=net.bytes_sent,
            bytes_received=net.bytes_recv,
            packets_sent=net.packets_sent,
            packets_received=net.packets_recv,
            errors_in=net.errin,
            errors_out=net.errout,
        ),
        process_count=len(psutil.pids()),
    )


__all__ = ["DiskUsage", "NetworkUsage", "ResourceSnapshot", "capture_resource_snapshot"]
