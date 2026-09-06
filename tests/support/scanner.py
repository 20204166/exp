"""Shared scanner fakes and patch environments for scanner/component tests.

``make_baseline_psutil`` returns a fresh healthy psutil-like object that
mirrors the standard dashboard environment (CPU/memory/swap/disk/network/
battery). Tests targeting one condition override individual methods. The
``scanner_environment`` context manager patches the exact ``maintenance.scanner``
lookup sites (psutil, platform system/release/machine, gpu, trash size, swap
devices) the dashboard scan path depends on.

Deliberately incomplete fakes remain possible: tests that exercise a missing
capability or an absent psutil must pass ``None`` or a partial object, never a
fully populated fake, so unintended scanner dependencies are not masked.
"""

import contextlib
from collections.abc import Iterator
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from maintenance.scanner import SystemScanner


def _cpu_freq() -> SimpleNamespace:
    return SimpleNamespace(current=2400.0, min=800.0, max=4000.0)


def make_baseline_psutil(**overrides: Any) -> SimpleNamespace:
    """Return a fresh, healthy psutil-like namespace with explicit overrides."""

    fake = SimpleNamespace(
        cpu_percent=lambda interval: 12.3,
        cpu_freq=lambda: _cpu_freq(),
        cpu_count=lambda logical: 8 if logical else 4,
        virtual_memory=lambda: SimpleNamespace(
            total=16 * 1024**3,
            used=8 * 1024**3,
            available=8 * 1024**3,
            percent=50.0,
        ),
        swap_memory=lambda: SimpleNamespace(
            total=4 * 1024**3,
            used=1 * 1024**3,
            percent=25.0,
        ),
        disk_usage=lambda _mount: SimpleNamespace(
            total=100 * 1024**3,
            used=40 * 1024**3,
            free=60 * 1024**3,
            percent=40.0,
        ),
        net_io_counters=lambda: SimpleNamespace(bytes_sent=1000, bytes_recv=2000),
        sensors_battery=lambda: SimpleNamespace(percent=75.0, power_plugged=True),
    )
    for name, value in overrides.items():
        setattr(fake, name, value)
    return fake


@contextmanager
def scanner_environment(
    scanner: SystemScanner,
    psutil_fake: Any,
    *,
    gpu_details: tuple[str, ...] = ("Test GPU",),
    trash_size: int = 2048,
    swap_devices: Any = (),
    system: str = "Linux",
    release: str = "6.1",
    machine: str = "x86_64",
    monotonic: float | None = None,
) -> Iterator[None]:
    """Patch the dashboard scan path around ``scanner`` for one body of work.

    The scanner instance must be created before entering so its CPU/GPU worker
    lifecycle is not left behind; callers own stopping it. ``monotonic`` pins
    the scanner's clock when a deterministic rate/elapsed-time assertion needs
    it.
    """

    patches = [
        patch("maintenance.scanner.psutil", psutil_fake),
        patch.object(scanner, "gpu_details", return_value=gpu_details),
        patch.object(SystemScanner, "trash_size", return_value=trash_size),
        patch.object(SystemScanner, "_swap_devices", return_value=swap_devices),
        patch("maintenance.scanner.platform.system", return_value=system),
        patch("maintenance.scanner.platform.release", return_value=release),
        patch("maintenance.scanner.platform.machine", return_value=machine),
    ]
    if monotonic is not None:
        patches.append(
            patch("maintenance.scanner.time.monotonic", return_value=monotonic)
        )
    with contextlib.ExitStack() as stack:
        for patcher in patches:
            stack.enter_context(patcher)
        yield
