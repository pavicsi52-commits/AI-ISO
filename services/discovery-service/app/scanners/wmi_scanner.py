"""WMI scanner, via the ``WMI``/``pywin32`` packages.

WMI is a Windows-only, COM/DCOM-based protocol with no cross-platform
implementation possible -- ``WMI``/``pywin32`` are declared in
``pyproject.toml`` with a ``sys_platform == 'win32'`` marker so
``uv sync``/``pip install`` simply skips them on this service's actual
Linux container deployment target, rather than failing to install (no
Linux wheel exists, and building pywin32's Windows API bindings from
source on Linux is not possible). :func:`probe` detects the missing
import at call time and reports a clear, honest failure rather than
letting an ``ImportError`` propagate as an unhandled exception.

**Verified locally against this development machine's own local WMI
provider** (``tests/test_scanner_wmi.py``, ``computer="localhost"``) --
this is the one scanner in this package that could be live-tested
*because* this particular development host happens to be Windows, not
because the target deployment environment is.
"""

from __future__ import annotations

import asyncio
import time

from app.models.enums import DiscoveryResultStatus, ProtocolType
from app.scanners.base import ProtocolScanner, ScanCredential, ScanOutcome

try:
    import pythoncom
    import wmi as wmi_module
except ImportError:  # pragma: no cover -- exercised only on non-Windows hosts
    pythoncom = None  # type: ignore[assignment]
    wmi_module = None


class WmiScanner(ProtocolScanner):
    """Connects to a host's WMI provider and reads its ``Win32_OperatingSystem`` info."""

    protocol = ProtocolType.WMI

    async def probe(
        self,
        address: str,
        *,
        port: int | None,
        timeout_seconds: float,
        credential: ScanCredential | None,
    ) -> ScanOutcome:
        if wmi_module is None or pythoncom is None:
            return ScanOutcome(
                status=DiscoveryResultStatus.FAILURE,
                error_message="WMI is only available on Windows hosts (WMI/pywin32 not installed).",
            )
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._connect, address, credential)

    def _connect(self, address: str, credential: ScanCredential | None) -> ScanOutcome:
        assert wmi_module is not None  # narrows for mypy -- already checked in probe()
        assert pythoncom is not None
        pythoncom.CoInitialize()
        start = time.perf_counter()
        try:
            kwargs: dict[str, object] = {"computer": address}
            if credential is not None and credential.username:
                kwargs["user"] = credential.username
                kwargs["password"] = credential.password or ""
            connection = wmi_module.WMI(**kwargs)
            systems = connection.Win32_OperatingSystem()
            latency_ms = (time.perf_counter() - start) * 1000
            if not systems:
                return ScanOutcome(
                    status=DiscoveryResultStatus.FAILURE,
                    latency_ms=latency_ms,
                    error_message="No Win32_OperatingSystem instance returned.",
                )
            os_info = systems[0]
            return ScanOutcome(
                status=DiscoveryResultStatus.SUCCESS,
                latency_ms=latency_ms,
                identity={
                    "caption": os_info.Caption,
                    "version": os_info.Version,
                    "build_number": os_info.BuildNumber,
                    "architecture": os_info.OSArchitecture,
                },
            )
        except wmi_module.x_wmi as exc:
            message = str(exc)
            if "access" in message.lower() or "denied" in message.lower():
                return ScanOutcome(status=DiscoveryResultStatus.AUTH_FAILED, error_message=message)
            return ScanOutcome(status=DiscoveryResultStatus.UNREACHABLE, error_message=message)
        finally:
            pythoncom.CoUninitialize()


__all__ = ["WmiScanner"]
