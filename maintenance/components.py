"""Unwired extraction draft for future maintenance components.

These helpers are intentionally not imported by the production code yet.
They document the intended seams so the next wiring step can stay small.
Current source references:
- `GpuDetector` from `maintenance/scanner.py:792-837`.
- `ScanCoordinator` from `window.py:394-451`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


class GpuDetector:
    """Select the correct GPU detail loader for the active platform.

    Extracted from the platform-dispatch path in
    `maintenance/scanner.py:792-837`.

    Intended to sit behind `SystemScanner.gpu_details()` once wiring is
    approved. Keeping the platform decision and fallback order here makes the
    scanner easier to split later without changing the public API today.
    """

    def __init__(
        self,
        *,
        system: Callable[[], str],
        nvidia_loader: Callable[[], tuple[str, ...] | None],
        mac_loader: Callable[[], tuple[str, ...]],
        windows_loader: Callable[[], tuple[str, ...]],
        linux_loader: Callable[[], tuple[str, ...]],
    ) -> None:
        self._system = system
        self._nvidia_loader = nvidia_loader
        self._mac_loader = mac_loader
        self._windows_loader = windows_loader
        self._linux_loader = linux_loader

    def detect(self) -> tuple[str, ...]:
        """Return the first applicable GPU detail set for this platform."""

        system = self._system()
        if system == "Darwin":
            # macOS keeps its native path first so the future wiring stays cheap.
            return self._mac_loader()

        nvidia_details = self._nvidia_loader()
        if nvidia_details:
            return nvidia_details

        if system == "Windows":
            return self._windows_loader()
        if system == "Linux":
            return self._linux_loader()
        return ("GPU information unavailable",)


@dataclass
class ScanCoordinator:
    """Track live scan state for the future Tk window split.

    Extracted from the live-scan coordination flow in `window.py:394-451`.

    Intended to back `window.AppWindow.handle_analyze()` and the delayed
    rescan logic. It keeps the in-flight flag, generation counter, and queued
    rerun request together so the UI can wait for the current loading cycle to
    finish before scheduling the next one.
    """

    active: bool = False
    generation: int = 0
    rerun_requested: bool = False

    def begin(self) -> tuple[int, bool]:
        """Start a scan or mark that one should run again after completion."""

        if self.active:
            self.rerun_requested = True
            return self.generation, False

        self.active = True
        self.generation += 1
        return self.generation, True

    def finish(self, generation: int) -> tuple[bool, bool]:
        """Finish the active generation and report whether a rerun is queued."""

        if generation != self.generation:
            return False, False

        self.active = False
        rerun = self.rerun_requested
        self.rerun_requested = False
        return True, rerun

    def cancel(self) -> None:
        """Clear the active state without scheduling another scan."""

        self.active = False
        self.rerun_requested = False
