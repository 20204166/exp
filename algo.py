import contextlib
import platform
import threading
from collections.abc import Callable
from typing import Any

from maintenance.components import require_psutil
from maintenance.components.gpu import nvidia_device_readings
from maintenance.components.scan_support import call_cancellable
from maintenance.models import (
    DashboardSnapshot,
    FileCandidate,
    ProcessCandidate,
    ResourceSummary,
)
from maintenance.scanner import ProgressCallback, SystemScanner

try:
    import psutil
except ImportError:
    psutil = None  # type: ignore[assignment]

try:
    import pynvml
except ImportError:
    pynvml = None


class Analyzer:
    """Collect system information for the interactive dashboard."""

    BYTES_IN_GIB = 1024**3
    GPU_DETAILS_UNAVAILABLE_MESSAGE = (
        "GPU details unavailable. For NVIDIA GPUs, run: "
        "python -m pip install nvidia-ml-py"
    )

    def __init__(
        self,
        memory_test_percent: float = 1.0,
        max_memory_test_gib: float = 1.0,
    ) -> None:
        """Validate the compatibility configuration parameters.

        The two parameters are a retained compatibility surface: they were
        consumed by the retired RAM test and remain accepted (and validated)
        so existing constructions such as the window's keep working.
        """
        if not 0 < memory_test_percent <= 5:
            raise ValueError("memory_test_percent must be between 0 and 5.")
        if max_memory_test_gib <= 0:
            raise ValueError("max_memory_test_gib must be greater than 0.")

        self.memory_test_percent = memory_test_percent
        self.max_memory_test_bytes = int(max_memory_test_gib * self.BYTES_IN_GIB)
        self.scanner = SystemScanner()

    @staticmethod
    def _require_psutil() -> Any:
        """Compatibility surface used by the catalog-referenced info methods."""
        return require_psutil(psutil)

    @classmethod
    def _format_bytes(cls, number_of_bytes: float) -> str:
        """Compatibility surface: legacy GiB formatting for the info methods."""
        return f"{number_of_bytes / cls.BYTES_IN_GIB:.2f} GiB"

    def cpu_info(self) -> list[str]:
        """Return CPU usage, core-count, and frequency information.

        Compatibility surface: referenced by the catalog ``loader_name``
        contract; the interactive dashboard does not call this.
        """
        psutil_module = self._require_psutil()
        frequency = psutil_module.cpu_freq()
        frequency_text = f"{frequency.current:.0f} MHz" if frequency else "Unavailable"

        return [
            f"CPU usage: {psutil_module.cpu_percent(interval=0.1):.1f}%",
            f"Physical cores: {psutil_module.cpu_count(logical=False) or 'Unknown'}",
            f"Logical cores: {psutil_module.cpu_count(logical=True) or 'Unknown'}",
            f"Current frequency: {frequency_text}",
        ]

    def memory_info(self) -> list[str]:
        """Return RAM and swap usage information.

        Compatibility surface: referenced by the catalog ``loader_name``
        contract; the interactive dashboard does not call this.
        """
        psutil_module = self._require_psutil()
        memory = psutil_module.virtual_memory()
        swap = psutil_module.swap_memory()

        return [
            f"RAM total: {self._format_bytes(memory.total)}",
            f"RAM used: {self._format_bytes(memory.used)} ({memory.percent:.1f}%)",
            f"RAM available: {self._format_bytes(memory.available)}",
            f"Swap total: {self._format_bytes(swap.total)}",
            f"Swap used: {self._format_bytes(swap.used)} ({swap.percent:.1f}%)",
        ]

    def storage_info(self) -> list[str]:
        """Return usage information for accessible storage partitions.

        Compatibility surface: referenced by the catalog ``loader_name``
        contract; the interactive dashboard does not call this.
        """
        psutil_module = self._require_psutil()
        lines: list[str] = []
        checked_mounts: set[str] = set()

        for partition in psutil_module.disk_partitions(all=False):
            mountpoint = partition.mountpoint
            if mountpoint in checked_mounts:
                continue

            checked_mounts.add(mountpoint)

            try:
                usage = psutil_module.disk_usage(mountpoint)
            except (OSError, PermissionError):
                continue

            name = partition.device or mountpoint
            lines.append(
                f"{name} ({mountpoint}): "
                f"{self._format_bytes(usage.used)} used, "
                f"{self._format_bytes(usage.free)} free, "
                f"{usage.percent:.1f}% full"
            )

        return lines or ["No accessible storage partitions were found."]

    def gpu_info(self) -> list[str]:
        """Return platform-appropriate GPU information when available.

        Compatibility surface: referenced by the catalog ``loader_name``
        contract; the interactive dashboard uses `scanner.gpu_details()`.
        """
        if platform.system() == "Darwin":
            return list(self.scanner.gpu_details())

        if pynvml is None:
            return [self.GPU_DETAILS_UNAVAILABLE_MESSAGE]

        try:
            pynvml.nvmlInit()
            return self._nvidia_gpu_lines()
        except Exception as error:  # noqa: BLE001 - GPU details are best-effort text.
            return [f"GPU details unavailable: {error}"]
        finally:
            self._shutdown_pynvml()

    def _nvidia_gpu_lines(self) -> list[str]:
        """Compatibility surface supporting `gpu_info` (NVML line format)."""

        if pynvml is None:
            return [self.GPU_DETAILS_UNAVAILABLE_MESSAGE]

        lines: list[str] = []
        for index, (
            name,
            memory_used,
            memory_total,
            usage_gpu,
            temperature,
        ) in enumerate(
            nvidia_device_readings(
                pynvml,
                include_temperature=True,
            )
        ):
            lines.extend(
                [
                    f"GPU {index}: {name}",
                    f"GPU usage: {usage_gpu}%",
                    (
                        f"GPU memory used: {self._format_bytes(memory_used)} "
                        f"of {self._format_bytes(memory_total)}"
                    ),
                    f"GPU temperature: {temperature}°C",
                ]
            )

        return lines or ["No NVIDIA GPU was detected."]

    @staticmethod
    def _shutdown_pynvml() -> None:
        """Compatibility surface supporting `gpu_info` (NVML shutdown)."""

        if pynvml is None:
            return

        with contextlib.suppress(Exception):
            pynvml.nvmlShutdown()

    def network_info(self) -> list[str]:
        """Return total network traffic since the computer started.

        Compatibility surface: referenced by the catalog ``loader_name``
        contract; the interactive dashboard does not call this.
        """
        psutil_module = self._require_psutil()
        network = psutil_module.net_io_counters()

        return [
            f"Data sent: {self._format_bytes(network.bytes_sent)}",
            f"Data received: {self._format_bytes(network.bytes_recv)}",
        ]

    def battery_info(self) -> list[str]:
        """Return battery information when the machine has a battery.

        Compatibility surface: referenced by the catalog ``loader_name``
        contract; the interactive dashboard does not call this.
        """
        psutil_module = self._require_psutil()
        battery = psutil_module.sensors_battery()

        if battery is None:
            return ["Battery information is unavailable."]

        state = "charging" if battery.power_plugged else "not charging"
        return [f"Battery: {battery.percent:.1f}% ({state})"]

    @staticmethod
    def _call_with_cancel(
        func: Callable[..., Any],
        cancel_event: threading.Event | None,
    ) -> Any:
        """Call `func`, passing `cancel_event` only when one is provided.

        Reuses the legacy-signature adapter shared by the scanner and
        dialogs: when an event is provided and an older one-argument hook
        rejects the keyword, the fallback runs under the same cancellation
        check (`check_cancelled`) used everywhere else, so a cancelled
        legacy hook never starts a fresh uncancellable run.
        """

        if cancel_event is None:
            return func()
        return call_cancellable(
            lambda: func(cancel_event=cancel_event),
            func,
            cancel_event,
        )

    def dashboard_snapshot(
        self,
        cancel_event: threading.Event | None = None,
        progress_callback: Callable[[str], None] | None = None,
    ) -> DashboardSnapshot:
        """Return structured data for the interactive dashboard."""
        return self.scanner.scan_dashboard(
            cancel_event=cancel_event,
            progress_callback=progress_callback,
        )

    def stop_background_workers(self) -> None:
        """Stop the persistent CPU sampler and abandon any in-flight GPU query.

        Called when the window closes so no scanner thread keeps sampling
        or publishing after the UI is gone.
        """

        self.scanner._stop_cpu_sampler()
        self.scanner._stop_gpu_query()

    def component_summary(
        self,
        key: str,
        cancel_event: threading.Event | None = None,
    ) -> ResourceSummary:
        """Scan one dashboard component independently and return its card."""
        return self._call_with_cancel(
            lambda event=None: self.scanner.scan_component(key, cancel_event=event),
            cancel_event,
        )

    def reset_component_sample(self, key: str) -> None:
        """Reset one component's persistent sample state (e.g. network rates).

        Called when a component resumes periodic polling after a pause so the
        first resumed sample is a fresh reading rather than a stale average.
        Components without persistent sample state are unaffected.
        """

        if key == "network":
            self.scanner._reset_network_sample()

    def process_candidates(
        self,
        cancel_event: threading.Event | None = None,
    ) -> list[ProcessCandidate]:
        """Return reviewable processes for the CPU and memory views."""
        return self._call_with_cancel(self.scanner.scan_processes, cancel_event)

    def storage_candidates(
        self,
        progress_callback: ProgressCallback | None = None,
        cancel_event: threading.Event | None = None,
    ) -> list[FileCandidate]:
        """Return large and duplicate files discovered in Downloads."""
        if progress_callback is None and cancel_event is None:
            return self.scanner.scan_downloads()
        return self.scanner.scan_downloads(
            progress_callback=progress_callback,
            cancel_event=cancel_event,
        )
