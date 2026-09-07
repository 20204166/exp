import contextlib
import ctypes
import getpass
import logging
import math
import os
import platform
import re
import subprocess
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, ClassVar, TypeGuard, TypeVar, cast

LOGGER = logging.getLogger(__name__)

_T = TypeVar("_T")


@dataclass(frozen=True)
class _NetworkObservation:
    """One best-effort read of the global/per-interface counters and interface stats.

    ``None`` means the corresponding query failed; an empty mapping means the
    query succeeded but produced no entries. Callers keep those two cases
    distinct (e.g. a disconnected host still reports up/down state).
    """

    global_counters: Any
    per_interface_counters: Any
    interface_stats: Any


from maintenance.components import (
    GPU_INFORMATION_UNAVAILABLE,
    PROTECTED_PROCESS_NAMES,
    DownloadsPathResolver,
    GpuDetector,
    HashFingerprint,
    ProgressCallback,
    ResourceFeatureCatalog,
    ScanCancelled,
    check_cancelled,
    gpu_unavailable_message,
    protected_process_pids,
    require_psutil,
    usernames_match,
    windows_windll,
)
from maintenance.components import (
    DownloadScanner as ComponentDownloadScanner,
)
from maintenance.components.gpu import (
    GpuProbe,
    gpu_probe_from_read,
    nvidia_device_readings,
)
from maintenance.components.process_safety import is_protected_process_name
from maintenance.components.scan_support import (
    BYTE_SCALE_UNITS,
    call_cancellable,
    detail_line_suffix,
    file_content_marker,
    file_sha256,
    stat_fingerprint,
    walk_directory_entries,
)
from maintenance.components.temperature import TemperatureSample, TemperatureScan
from maintenance.external_commands import run_json_command, run_text_command
from maintenance.models import (
    CapabilityState,
    DashboardSnapshot,
    FileCandidate,
    ProcessCandidate,
    ResourceSummary,
    unavailable_summary,
)

try:
    import psutil
except ImportError:
    psutil = None  # type: ignore[assignment]

try:
    import pynvml
except ImportError:
    pynvml = None


class _RecycleBinInfo(ctypes.Structure):
    _fields_ = [
        ("cb_size", ctypes.c_ulong),
        ("size", ctypes.c_longlong),
        ("item_count", ctypes.c_longlong),
    ]


class SystemScanner:
    """Read system state and discover reviewable cleanup candidates."""

    LARGE_FILE_BYTES: int = 100 * 1024**2
    DUPLICATE_MIN_BYTES: int = 1024**2
    HASH_CHUNK_BYTES: int = 1024**2
    HASH_CACHE_MAX_ENTRIES: int = 1024
    PROCESS_MIN_BYTES: int = 10 * 1024**2
    PROCESS_ACTIVITY_MIN_CPU_PERCENT: float = 1.0
    PROCESS_SAMPLE_SECONDS: float = 0.25
    CPU_PERCENT_SAMPLE_SECONDS: float = 0.2
    CPU_WORKER_TIMEOUT_SECONDS: float = 5.0
    CPU_CANCEL_POLL_SECONDS: float = 0.05
    TEMPERATURE_REFRESH_SECONDS: float = 5.0
    TRASH_SIZE_REFRESH_SECONDS: float = 60.0
    GPU_COMMAND_TIMEOUT_SECONDS: int = 10
    GPU_QUERY_TIMEOUT_SECONDS: float = 12.0
    GPU_QUERY_ABANDON_SECONDS: float = 60.0
    GPU_QUERY_TIMEOUT_MESSAGE = f"{GPU_INFORMATION_UNAVAILABLE}: query timed out"

    COMPONENT_KEYS: tuple[str, ...] = tuple(
        feature.key for feature in ResourceFeatureCatalog().all()
    )

    COMPONENT_TITLES: ClassVar[dict[str, str]] = {
        feature.key: feature.title for feature in ResourceFeatureCatalog().all()
    }

    TUNNEL_INTERFACE_PREFIXES: frozenset[str] = frozenset(
        {"tun", "tap", "utun", "ppp", "ipsec", "wg"}
    )

    CPU_TEMP_DRIVERS: tuple[str, ...] = (
        "coretemp",
        "k10temp",
        "zenpower",
        "cpu_thermal",
        "x86_pkg_temp",
        "acpitz",
    )
    GPU_TEMP_DRIVERS: tuple[str, ...] = ("amdgpu", "nouveau", "radeon")
    NVME_TEMP_DRIVERS: tuple[str, ...] = ("nvme",)

    GPU_VENDOR_TAGS: frozenset[str] = frozenset({"amd", "ati", "amd/ati"})
    GPU_VENDOR_PREFIXES: tuple[str, ...] = (
        "Advanced Micro Devices, Inc. ",
        "Advanced Micro Devices, Inc., ",
        "NVIDIA Corporation ",
        "Intel Corporation ",
        "Corporation ",
    )
    GPU_REVISION_PATTERN: ClassVar[re.Pattern[str]] = re.compile(
        r"\s*\(rev [0-9a-fA-F.]+\)$"
    )

    PROTECTED_PROCESS_NAMES = PROTECTED_PROCESS_NAMES

    def __init__(self, downloads_path: Path | None = None) -> None:
        self.downloads_path = downloads_path or self._default_downloads_path()
        self._download_scanner = ComponentDownloadScanner(self.downloads_path)
        self._hash_cache: OrderedDict[Path, tuple[HashFingerprint, bytes, str]] = (
            self._download_scanner._hash_cache
        )
        self._hash_cache_lock = self._download_scanner._hash_cache_lock
        self._downloads_scan_lock = self._download_scanner._downloads_scan_lock
        self._static_gpu_details: tuple[str, ...] | None = None
        self._static_gpu_lock = threading.Lock()
        self._nvml_probe_failed = False
        self._gpu_query_lock = threading.Lock()
        self._gpu_query_in_flight = False
        self._gpu_query_generation = 0
        self._gpu_query_timed_out_at: float | None = None
        self._gpu_capabilities_by_thread: dict[int, CapabilityState] = {}
        self._static_hardware_lock = threading.Lock()
        self._static_system_label: str | None = None
        self._static_system_label_fingerprint: tuple[Any, ...] | None = None
        self._static_cpu_cores: tuple[int | None, int | None] | None = None
        self._static_cpu_cores_fingerprint: tuple[Any, ...] | None = None
        self._static_gpu_fingerprint: tuple[Any, ...] | None = None
        self._network_sample: tuple[float, int, int] | None = None
        self._network_sample_lock = threading.Lock()
        self._temperature_cache: tuple[float, TemperatureScan] | None = None
        self._temperature_cache_lock = threading.Lock()
        self._trash_size_cache: tuple[float, int] | None = None
        self._trash_size_cache_lock = threading.Lock()
        self._cpu_read_lock = threading.Lock()
        self._cpu_request_lock = threading.RLock()
        self._cpu_seeded = False
        self._cpu_request_event = threading.Event()
        self._cpu_result_event = threading.Event()
        self._cpu_value: float | None = None
        self._cpu_error: str | None = None
        self._cpu_stop_event = threading.Event()
        self._cpu_worker: threading.Thread | None = None
        self._cpu_last_logged_error: str | None = None

    def _sync_download_scanner(self) -> ComponentDownloadScanner:
        scanner = self._download_scanner
        scanner.downloads_path = self.downloads_path
        scanner.LARGE_FILE_BYTES = self.LARGE_FILE_BYTES
        scanner.DUPLICATE_MIN_BYTES = self.DUPLICATE_MIN_BYTES
        scanner.HASH_CHUNK_BYTES = self.HASH_CHUNK_BYTES
        scanner.HASH_CACHE_MAX_ENTRIES = self.HASH_CACHE_MAX_ENTRIES
        scanner._check_cancelled = self._check_cancelled  # type: ignore[attr-defined,method-assign]
        scanner._file_hash = self._download_file_hash  # type: ignore[attr-defined,method-assign]
        scanner._file_content_marker = self._download_file_content_marker  # type: ignore[attr-defined,method-assign]
        return scanner

    @classmethod
    def _make_downloads_path_resolver(cls) -> DownloadsPathResolver:
        resolver = DownloadsPathResolver()
        resolver._windows_downloads_path = cls._windows_downloads_path  # type: ignore[attr-defined,method-assign]
        resolver._is_directory = cls._is_directory  # type: ignore[attr-defined,method-assign]
        resolver._path_exists = cls._path_exists  # type: ignore[attr-defined,method-assign]
        resolver._safe_downloads_fallback = cls._safe_downloads_fallback  # type: ignore[attr-defined,method-assign]
        return resolver

    def _download_file_hash(
        self,
        path: Path,
        cancel_event: threading.Event | None = None,
    ) -> str:
        return call_cancellable(
            lambda: self._file_hash(path, cancel_event=cancel_event),
            lambda: self._file_hash(path),
            cancel_event,
        )

    def _download_file_content_marker(
        self,
        path: Path,
        cancel_event: threading.Event | None = None,
    ) -> bytes:
        return call_cancellable(
            lambda: self._file_content_marker(path, cancel_event=cancel_event),
            lambda: self._file_content_marker(path),
            cancel_event,
        )

    @staticmethod
    def _require_psutil() -> Any:
        return require_psutil(psutil)

    @staticmethod
    def _byte_unit(value: float) -> tuple[int, str]:
        """Return the (scale, unit) of the largest unit a value fits in.

        The scale/unit table is shared with `maintenance.health` so the
        units the scanner prints are always the units health parses.
        """

        for scale, unit in BYTE_SCALE_UNITS:
            if abs(value) >= scale:
                return scale, unit
        return 1, "B"

    @classmethod
    def format_bytes(cls, number_of_bytes: float) -> str:
        value = float(number_of_bytes)
        scale, unit = cls._byte_unit(value)
        return f"{value / scale:.2f} {unit}"

    def scan_dashboard(
        self,
        cancel_event: threading.Event | None = None,
        progress_callback: Callable[[str], None] | None = None,
    ) -> DashboardSnapshot:
        self._check_cancelled(cancel_event)
        self._invalidate_trash_size()
        resources = []
        for key in self.COMPONENT_KEYS:
            self._check_cancelled(cancel_event)
            if progress_callback is not None:
                progress_callback(f"Scanning {self._component_title(key)}...")
            resources.append(self.scan_component(key, cancel_event))
        self._check_cancelled(cancel_event)
        return DashboardSnapshot(
            system_label=self._system_label(),
            scanned_at=datetime.now(timezone.utc).astimezone(),
            resources=tuple(resources),
        )

    @staticmethod
    def _component_title(key: str) -> str:
        return SystemScanner.COMPONENT_TITLES.get(key, key)

    def scan_component(
        self,
        key: str,
        cancel_event: threading.Event | None = None,
    ) -> ResourceSummary:
        """Scan one dashboard component independently and return its card.

        Each component reads only its own sensors, so one slow or failing
        component never delays the others. Static hardware (CPU cores, GPU
        model, system label) stays cached; live values are re-read here.
        """

        self._check_cancelled(cancel_event)
        psutil_module: Any = psutil

        if key == "cpu":
            cpu_percent = self._component_value(
                lambda: self._read_cpu_percent(psutil_module, cancel_event)
            )
            frequency = self._component_value(lambda: psutil_module.cpu_freq())
            temperature_scan = self._cached_temperature_scan(psutil_module)
            return self._resource_with_fallback(
                lambda: self._cpu_resource(
                    cpu_percent,
                    frequency,
                    list(temperature_scan.lines),
                    temperature_scan.samples_for("cpu"),
                ),
                "cpu",
                self._component_title("cpu"),
            )

        if key == "memory":
            memory = self._component_value(lambda: psutil_module.virtual_memory())
            swap = self._component_value(lambda: psutil_module.swap_memory())
            return self._resource_with_fallback(
                lambda: self._memory_resource(memory, swap),
                "memory",
                self._component_title("memory"),
            )

        if key == "storage":
            disk = self._component_value(
                lambda: psutil_module.disk_usage(str(Path.home()))
            )
            trash_bytes = self._safe_trash_size()
            temperature_scan = self._cached_temperature_scan(psutil_module)
            return self._resource_with_fallback(
                lambda: self._storage_resource(
                    disk,
                    trash_bytes,
                    list(temperature_scan.lines),
                    temperature_scan.samples_for("storage"),
                ),
                "storage",
                self._component_title("storage"),
            )

        if key == "gpu":
            details = self.gpu_details()
            capability = self._gpu_capability_for_thread()
            temperature_scan = self._cached_temperature_scan(psutil_module)
            return self._resource_with_fallback(
                lambda: self._gpu_resource(
                    details,
                    list(temperature_scan.lines),
                    temperature_scan.samples_for("gpu"),
                    capability=capability,
                ),
                "gpu",
                self._component_title("gpu"),
            )

        if key == "network":
            observation = self._read_network_observation(psutil_module)
            capability = self._network_capability(observation)
            return self._resource_with_fallback(
                lambda: self._network_resource(
                    observation,
                    capability=capability,
                ),
                "network",
                self._component_title("network"),
            )

        if key == "battery":
            battery, battery_error = self._read_battery(psutil_module)
            temperature_scan = self._cached_temperature_scan(psutil_module)
            return self._resource_with_fallback(
                lambda: self._battery_resource(
                    battery,
                    battery_error,
                    list(temperature_scan.lines),
                    temperature_scan.samples_for("battery"),
                ),
                "battery",
                self._component_title("battery"),
            )

        raise ValueError(f"Unknown component: {key}")

    @staticmethod
    def _psutil_value(query: Callable[[], Any]) -> Any:
        """Return one psutil reading, or None when the reading fails."""

        try:
            return query()
        except ScanCancelled:
            raise
        except Exception as error:  # noqa: BLE001 - one failed sensor must not fail the scan.
            LOGGER.warning("Sensor read failed: %s", error)
            return None

    def _component_value(self, query: Callable[[], Any]) -> Any:
        """Read one component sensor, or None when psutil is unavailable.

        Per-component scans use this so the missing-psutil case is handled in
        exactly one place instead of in every component branch.
        """

        if psutil is None:
            return None
        return self._psutil_value(query)

    def _read_cpu_percent(
        self,
        psutil_module: Any,
        cancel_event: threading.Event | None = None,
    ) -> float | None:
        """Return one CPU usage reading without blocking after a baseline.

        The first read per scanner takes one short blocking sample
        (`CPU_PERCENT_SAMPLE_SECONDS`, matching the previous behaviour) and
        starts a persistent daemon worker. Every later read asks that worker
        for a non-blocking `psutil.cpu_percent(interval=None)` delta, whose
        window equals the request spacing (roughly the 1 second component
        refresh cadence), so no worker ever sleeps.
        """

        with self._cpu_read_lock:
            if not self._cpu_seeded:
                value = self._psutil_value(
                    lambda: psutil_module.cpu_percent(
                        interval=self.CPU_PERCENT_SAMPLE_SECONDS
                    )
                )
                if value is None:
                    return None
                self._cpu_seeded = True
                self._start_cpu_worker()
                return value
        return self._request_cpu_sample(cancel_event)

    def _request_cpu_sample(
        self,
        cancel_event: threading.Event | None = None,
    ) -> float | None:
        """Request one non-blocking delta from the persistent CPU worker."""

        with self._cpu_request_lock:
            if self._cpu_worker is None or not self._cpu_worker.is_alive():
                self._start_cpu_worker()
            self._cpu_result_event.clear()
            self._cpu_request_event.set()
            if not self._wait_for_cpu_result(cancel_event):
                self._start_cpu_worker()
                return None
            if self._cpu_error is not None:
                return None
            return self._cpu_value

    def _wait_for_cpu_result(
        self,
        cancel_event: threading.Event | None,
    ) -> bool:
        """Wait for one sampler result, honouring cancellation when given.

        Without a cancel event this is exactly one bounded wait on the result
        event (the historical behaviour). With one, the wait is sliced so a
        cancelled scan raises `ScanCancelled` instead of blocking out the full
        worker timeout.
        """

        if cancel_event is None:
            return self._cpu_result_event.wait(self.CPU_WORKER_TIMEOUT_SECONDS)

        deadline = time.monotonic() + self.CPU_WORKER_TIMEOUT_SECONDS
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            if self._cpu_result_event.wait(
                min(self.CPU_CANCEL_POLL_SECONDS, remaining)
            ):
                return True
            self._check_cancelled(cancel_event)

    def _start_cpu_worker(self) -> None:
        """Start (or restart) the persistent CPU delta worker thread."""

        with self._cpu_request_lock:
            worker = self._cpu_worker
            if worker is not None and worker.is_alive():
                return
            self._cpu_stop_event.clear()
            self._cpu_request_event.clear()
            self._cpu_result_event.clear()
            try:
                worker = threading.Thread(
                    target=self._cpu_worker_loop,
                    daemon=True,
                )
                worker.start()
            except RuntimeError as error:
                LOGGER.warning("CPU sampler start failed: %s", error)
                self._cpu_worker = None
                return
            self._cpu_worker = worker

    def _cpu_worker_loop(self) -> None:
        """Serve one non-blocking CPU delta per request.

        psutil keeps its non-blocking delta baseline per thread id, so the
        worker first arms its own baseline with a discarded reading, then
        answers requests with deltas since the previous request.
        """

        psutil_module: Any = psutil
        if psutil_module is not None:
            with contextlib.suppress(Exception):
                psutil_module.cpu_percent(interval=None)

        while not self._cpu_stop_event.is_set():
            try:
                self._cpu_request_event.wait()
            except Exception:  # noqa: BLE001 - a broken wait must not kill the worker.
                break
            self._cpu_request_event.clear()
            if self._cpu_stop_event.is_set():
                return
            self._publish_cpu_sample(self._cpu_sample_once())

    def _cpu_sample_once(self) -> tuple[float | None, str | None]:
        """Take one non-blocking system CPU reading or report its error."""

        try:
            psutil_module: Any = psutil
            if psutil_module is None:
                return None, "psutil is not installed"
            return float(psutil_module.cpu_percent(interval=None)), None
        except Exception as error:  # noqa: BLE001 - sampler failures degrade one card.
            return None, str(error)

    def _publish_cpu_sample(
        self,
        sample: tuple[float | None, str | None],
    ) -> None:
        """Store one sampler result, wake the requestor, and log at most
        once per consecutive-failure streak."""

        value, error = sample
        with self._cpu_read_lock:
            self._cpu_value = value
            self._cpu_error = error
        if error is not None:
            if error != self._cpu_last_logged_error:
                LOGGER.warning("CPU sample failed: %s", error)
                self._cpu_last_logged_error = error
        else:
            self._cpu_last_logged_error = None
        self._cpu_result_event.set()

    def _stop_cpu_sampler(self) -> None:
        """Stop the persistent CPU worker thread (idempotent)."""

        self._cpu_stop_event.set()
        self._cpu_request_event.set()
        worker = self._cpu_worker
        if worker is not None and worker.is_alive():
            worker.join(timeout=1.0)
        self._cpu_worker = None

    def _stop_gpu_query(self) -> None:
        """Abandon any in-flight GPU query (idempotent).

        Bumping the generation makes a running worker's finally a no-op, so a
        late completion can never clear a newer query's state. No join: a
        wedged NVML call is uninterruptible, so we only invalidate, never
        wait.
        """

        with self._gpu_query_lock:
            self._gpu_query_generation += 1
            self._gpu_query_in_flight = False
            self._gpu_query_timed_out_at = None

    def _safe_trash_size(self) -> int:
        """Return the trash size without letting a storage failure fail the scan.

        The recursive trash walk is cached for `TRASH_SIZE_REFRESH_SECONDS`
        via the shared TTL-cache engine, so ordinary storage refreshes do
        not re-walk a large Trash tree on every tick. A full dashboard scan
        invalidates the cache first, so user-initiated scans and post-cleanup
        rescans always show the exact fresh value. A failed walk is never
        cached, so it retries on the next refresh.
        """

        try:
            return self._ttl_cached_value(
                lock=self._trash_size_cache_lock,
                cache_name="_trash_size_cache",
                ttl_seconds=self.TRASH_SIZE_REFRESH_SECONDS,
                loader=self.trash_size,
            )
        except Exception as error:  # noqa: BLE001 - storage sub-component must not fail the scan.
            LOGGER.warning("Trash size read failed: %s", error)
            return 0

    def _invalidate_trash_size(self) -> None:
        """Clear the cached trash size so the next read re-walks it."""

        with self._trash_size_cache_lock:
            self._trash_size_cache = None

    def _static_fingerprint(self) -> tuple[Any, ...]:
        """Identity of the machine and boot session for the static cache.

        When either changes (a different host or a new boot session), cached
        static hardware is treated as stale and re-read on the next scan.
        """

        boot_time: Any = None
        if psutil is not None:
            try:
                boot_time = psutil.boot_time()
            except Exception as error:  # noqa: BLE001 - boot time is a best-effort signal.
                LOGGER.warning("Boot time read failed: %s", error)
                boot_time = None
        return (platform.node(), boot_time)

    def _system_label(self) -> str:
        """Return the OS/kernel label, cached until the machine or boot changes."""

        return self._cached_fingerprint_value(
            lock=self._static_hardware_lock,
            value_name="_static_system_label",
            fingerprint_name="_static_system_label_fingerprint",
            fingerprint=self._static_fingerprint(),
            loader=lambda: (
                f"{platform.system()} {platform.release()} • {platform.machine()}"
            ),
        )

    def _cpu_core_counts(self) -> tuple[int | None, int | None]:
        """Return physical/logical core counts, cached until hardware changes.

        A failed read is not cached, so a transient error recovers on the next
        scan, and the error propagates so the CPU card alone degrades.
        """

        def read_cores() -> tuple[int | None, int | None]:
            psutil_module = self._require_psutil()
            return (
                psutil_module.cpu_count(logical=False),
                psutil_module.cpu_count(logical=True),
            )

        return self._cached_fingerprint_value(
            lock=self._static_hardware_lock,
            value_name="_static_cpu_cores",
            fingerprint_name="_static_cpu_cores_fingerprint",
            fingerprint=self._static_fingerprint(),
            loader=read_cores,
        )

    def _cached_fingerprint_value(
        self,
        *,
        lock: Any,
        value_name: str,
        fingerprint_name: str,
        fingerprint: tuple[Any, ...],
        loader: Callable[[], _T],
        acceptable: Callable[[_T], bool] | None = None,
    ) -> _T:
        """Return one fingerprint-invalidated cached value, computing it once.

        The cached value lives in the ``value_name`` instance slot and is
        reused while the ``fingerprint_name`` slot holds the current
        fingerprint (host/boot identity). A value is stored only when the
        ``loader`` succeeds and ``acceptable`` allows it, so failed or
        unavailable reads are never cached and retry on the next scan.
        """

        with lock:
            value = getattr(self, value_name)
            if value is not None and getattr(self, fingerprint_name) == fingerprint:
                return cast(_T, value)

        computed = loader()
        if acceptable is None or acceptable(computed):
            with lock:
                setattr(self, fingerprint_name, fingerprint)
                setattr(self, value_name, computed)
        return computed

    def _ttl_cached_value(
        self,
        *,
        lock: Any,
        cache_name: str,
        ttl_seconds: float,
        loader: Callable[[], _T],
    ) -> _T:
        """Return one time-based cached value, re-loading it after a TTL.

        The cached ``(monotonic timestamp, value)`` tuple lives in the
        ``cache_name`` instance slot; a value is stored only after the
        ``loader`` succeeds, so a failing loader is never cached and retries
        on the next call. Shared by the temperature and trash-size caches.
        """

        with lock:
            cached = getattr(self, cache_name)
            now = time.monotonic()
            if cached is not None and now - cached[0] < ttl_seconds:
                return cached[1]

        value = loader()
        with lock:
            setattr(self, cache_name, (time.monotonic(), value))
        return value

    def reset_static_cache(self) -> None:
        """Drop all cached static hardware so the next scan re-reads it.

        Static values are invalidated automatically when the boot session or
        machine identity changes; this method forces a fresh read for tests and
        any future "rescan hardware" control.
        """

        with self._static_hardware_lock:
            self._static_system_label = None
            self._static_system_label_fingerprint = None
            self._static_cpu_cores = None
            self._static_cpu_cores_fingerprint = None
        with self._static_gpu_lock:
            self._static_gpu_details = None
            self._static_gpu_fingerprint = None
            self._nvml_probe_failed = False

    def _resource_with_fallback(
        self,
        builder: Callable[[], ResourceSummary],
        key: str,
        title: str,
    ) -> ResourceSummary:
        """Build one dashboard card, degrading it alone when it fails."""

        try:
            return builder()
        except ScanCancelled:
            raise
        except Exception as error:  # noqa: BLE001 - one failed card must not fail the scan.
            LOGGER.warning("Resource %r failed: %s", key, error)
            return unavailable_summary(key, title)

    def _cpu_resource(
        self,
        cpu_percent: float | None,
        frequency: Any,
        temperature_lines: list[str],
        temperature_samples: tuple[TemperatureSample, ...] = (),
    ) -> ResourceSummary:
        physical_cores, logical_cores = self._cpu_core_counts()
        details: tuple[str, ...] = (
            f"Physical cores: {physical_cores or 'Unknown'}",
            f"Logical cores: {logical_cores or 'Unknown'}",
            self._frequency_detail(frequency),
        )
        cpu_temperature = self._temperature_value(temperature_lines, "CPU")
        if cpu_temperature is not None:
            details += (f"Temperature: {cpu_temperature}",)

        return ResourceSummary(
            key="cpu",
            title="CPU",
            value=f"{cpu_percent:.1f}%",
            subtitle="Current processor usage",
            percent=cpu_percent,
            details=details,
            actionable=True,
            capability=CapabilityState.SUPPORTED,
            temperatures=temperature_samples,
        )

    @staticmethod
    def _frequency_detail(frequency: Any) -> str:
        """Render one CPU-frequency reading as a stable detail line.

        ``frequency`` is a psutil ``scpufreq`` value (or ``None``). Missing,
        zero, or reversed min/max fields are tolerated so unusual or
        unavailable frequency reporting never fails the CPU card.
        """

        current = getattr(frequency, "current", None)
        if not isinstance(current, (int, float)) or current <= 0:
            return "Current frequency: Unavailable"

        maximum = getattr(frequency, "max", None)
        if isinstance(maximum, (int, float)) and maximum > 0 and maximum >= current:
            return (
                f"Current frequency: {current / 1000:.2f} GHz / "
                f"Max {maximum / 1000:.2f} GHz"
            )
        return f"Current frequency: {current / 1000:.2f} GHz"

    def _memory_resource(self, memory: Any, swap: Any) -> ResourceSummary:
        total = memory.total
        available = memory.available
        in_use = max(total - available, 0)
        swap_lines = self._swap_details(swap, self._swap_devices())

        return ResourceSummary(
            key="memory",
            title="Memory",
            value=f"{memory.percent:.1f}%",
            subtitle=f"{self.format_bytes(available)} available",
            percent=memory.percent,
            details=(
                f"Physical RAM: {self.format_bytes(total)}",
                f"Available: {self.format_bytes(available)}",
                f"In use: {self.format_bytes(in_use)} ({memory.percent:.1f}%)",
                *swap_lines,
            ),
            actionable=True,
            capability=CapabilityState.SUPPORTED,
        )

    @staticmethod
    def _swap_devices() -> list[tuple[str, int, int]]:
        """Return Linux swap devices as ``(name, size_bytes, used_bytes)``.

        zram is reported by name so the memory card can keep compressed RAM
        separate from disk-backed swap. On other platforms, or when the kernel
        table cannot be read, an empty list is returned and callers fall back
        to the aggregate psutil reading.
        """

        if platform.system() != "Linux":
            return []

        try:
            lines = Path("/proc/swaps").read_text().splitlines()
        except OSError:
            return []

        devices: list[tuple[str, int, int]] = []
        for line in lines[1:]:
            parts = line.split()
            if len(parts) < 4:
                continue
            try:
                size_bytes = int(parts[2]) * 1024
                used_bytes = int(parts[3]) * 1024
            except ValueError:
                continue
            devices.append((parts[0], size_bytes, used_bytes))
        return devices

    @staticmethod
    def _is_zram_device(name: str) -> bool:
        """Return whether a swap device name is compressed-RAM (zram)."""

        return name.startswith("/dev/zram")

    def _swap_details(
        self,
        swap: Any,
        devices: list[tuple[str, int, int]],
    ) -> tuple[str, ...]:
        """Build the swap detail lines, keeping zram and disk swap distinct."""

        if devices:
            total = sum(size for _, size, _ in devices)
            used = sum(used_bytes for _, _, used_bytes in devices)
            lines = [
                f"Swap: {self.format_bytes(used)} used of {self.format_bytes(total)}"
            ]

            zram_total = sum(
                size for name, size, _ in devices if self._is_zram_device(name)
            )
            zram_used = sum(
                used_bytes
                for name, _, used_bytes in devices
                if self._is_zram_device(name)
            )
            disk_total = sum(
                size for name, size, _ in devices if not self._is_zram_device(name)
            )
            disk_used = sum(
                used_bytes
                for name, _, used_bytes in devices
                if not self._is_zram_device(name)
            )
            if zram_total or zram_used:
                lines.append(
                    f"zram: {self.format_bytes(zram_used)} of "
                    f"{self.format_bytes(zram_total)}"
                )
            if disk_total or disk_used:
                lines.append(
                    f"Disk-backed swap: {self.format_bytes(disk_used)} of "
                    f"{self.format_bytes(disk_total)}"
                )
            return tuple(lines)

        if swap is None:
            return ("Swap: Unavailable",)
        if swap.total <= 0:
            return ("Swap: none configured",)
        return (
            (
                f"Swap: {self.format_bytes(swap.used)} used of "
                f"{self.format_bytes(swap.total)} ({swap.percent:.1f}%)"
            ),
        )

    def _storage_resource(
        self,
        disk: Any,
        trash_bytes: int,
        temperature_lines: list[str],
        temperature_samples: tuple[TemperatureSample, ...] = (),
    ) -> ResourceSummary:
        details: tuple[str, ...] = (
            f"Main disk: {Path.home()}",
            f"Total: {self.format_bytes(disk.total)}",
            f"Used: {self.format_bytes(disk.used)}",
            f"Free: {self.format_bytes(disk.free)}",
            f"Downloads: {self.downloads_path}",
            f"Trash size: {self.format_bytes(trash_bytes)}",
        )
        drive_temperature = self._temperature_value(temperature_lines, "NVMe")
        if drive_temperature is not None:
            details += (f"Drive temperature: {drive_temperature}",)

        return ResourceSummary(
            key="storage",
            title="Storage",
            value=f"{disk.percent:.1f}%",
            subtitle=f"{self.format_bytes(disk.free)} free",
            percent=disk.percent,
            details=details,
            actionable=True,
            capability=CapabilityState.SUPPORTED,
            temperatures=temperature_samples,
        )

    def _gpu_resource(
        self,
        gpu_details: tuple[str, ...],
        temperature_lines: list[str],
        temperature_samples: tuple[TemperatureSample, ...] = (),
        capability: CapabilityState = CapabilityState.UNKNOWN,
    ) -> ResourceSummary:
        details = gpu_details
        gpu_temperature = self._temperature_value(temperature_lines, "GPU")
        if gpu_temperature is not None:
            details += (f"Temperature: {gpu_temperature}",)

        unavailable = gpu_details[0].startswith(GPU_INFORMATION_UNAVAILABLE)
        return ResourceSummary(
            key="gpu",
            title="GPU",
            value=self._gpu_display_name(gpu_details),
            subtitle=(
                "Information unavailable" if unavailable else "Graphics hardware"
            ),
            percent=None,
            details=details,
            failed=unavailable,
            capability=capability,
            temperatures=temperature_samples,
        )

    @classmethod
    def _gpu_display_name(cls, gpu_details: tuple[str, ...]) -> str:
        """Return a concise card name for the first GPU detail line.

        The full raw/canonical identifier stays in ``gpu_details`` (and
        therefore in View Details); only the overview headline is shortened
        when a trustworthy concise name can be derived, otherwise the raw
        line is returned unchanged.
        """

        raw = gpu_details[0]
        concise = cls._concise_gpu_name(raw)
        return concise or raw

    @classmethod
    def _concise_gpu_name(cls, raw: str) -> str | None:
        """Derive a concise GPU product name, or None when unsure.

        Only lspci-style descriptions (a ``[...]`` group or a known vendor
        prefix) are rewritten, so NVML, macOS, Windows, unavailable, and
        short names pass through untouched and no model is ever fabricated.
        """

        line = raw.strip()
        brackets = re.findall(r"\[([^\]]+)\]", line)
        if brackets:
            candidate: str | None = None
            for group in reversed(brackets):
                product = group.rsplit("[", 1)[-1].strip()
                if product and product.casefold() not in cls.GPU_VENDOR_TAGS:
                    candidate = product
                    break
            if candidate is None:
                candidate = line.rsplit("]", 1)[-1]
        else:
            for prefix in cls.GPU_VENDOR_PREFIXES:
                if line.startswith(prefix):
                    candidate = line[len(prefix) :]
                    break
            else:
                return None

        candidate = cls.GPU_REVISION_PATTERN.sub("", candidate)
        candidate = candidate.strip().lstrip(",; ")
        return candidate or None

    def _read_network_observation(self, psutil_module: Any) -> _NetworkObservation:
        """Read every network sensor once and carry it through one component scan.

        Global counters use ``_component_value`` (missing-psutil aware), while
        the per-interface counters and interface stats use the best-effort
        ``_psutil_value`` boundary. A ``None`` field means its query failed; an
        empty mapping means the query succeeded with no entries.
        """

        return _NetworkObservation(
            global_counters=self._component_value(
                lambda: psutil_module.net_io_counters()
            ),
            per_interface_counters=SystemScanner._psutil_value(
                lambda: psutil_module.net_io_counters(pernic=True)
            ),
            interface_stats=SystemScanner._psutil_value(
                lambda: psutil_module.net_if_stats()
            ),
        )

    def _network_resource(
        self,
        observation: _NetworkObservation,
        capability: CapabilityState = CapabilityState.UNKNOWN,
    ) -> ResourceSummary:
        network = observation.global_counters
        received = network.bytes_recv
        sent = network.bytes_sent
        down_rate, up_rate = self._sample_network_rates(network)
        up_interfaces = self._up_interface_names(observation.interface_stats)
        interface = self._active_interface_from_counters(
            observation.per_interface_counters,
            up_interfaces,
        )
        vpn_interface = self._vpn_interface_from_names(up_interfaces)

        if down_rate is not None and up_rate is not None:
            down_text, up_text = self._rate_pair_text(down_rate, up_rate)
            value = f"↓ {down_text}  ↑ {up_text}"
        else:
            down_text = up_text = "—"
            value = "—"

        if interface:
            subtitle = f"Active: {interface}"
            interface_detail = interface
        elif up_interfaces == set():
            subtitle = "Disconnected"
            interface_detail = "none"
        else:
            subtitle = "No active interface"
            interface_detail = "Unknown"

        return ResourceSummary(
            key="network",
            title="Network",
            value=value,
            subtitle=subtitle,
            percent=None,
            details=(
                f"Download rate: {down_text}",
                f"Upload rate: {up_text}",
                f"Received this boot: {self.format_bytes(received)}",
                f"Sent this boot: {self.format_bytes(sent)}",
                f"Active interface: {interface_detail}",
                f"VPN: {'Connected' if vpn_interface else 'Not detected'}",
            ),
            capability=capability,
        )

    def _network_capability(
        self,
        observation: _NetworkObservation,
    ) -> CapabilityState:
        """Classify network capability from authoritative probe outcomes.

        Global counters succeeding means the network capability exists (a
        disconnected or down adapter is still a supported card). Absence is
        only claimed when at least one authoritative inventory (per-interface
        counters or interface stats) succeeds and neither shows a non-loopback
        adapter. If every detail probe fails, the card is treated as
        ``SUPPORTED`` (it exists) rather than absent.
        """

        if observation.global_counters is None:
            return CapabilityState.UNKNOWN
        pernic = observation.per_interface_counters
        stats = observation.interface_stats

        if pernic and any(
            not SystemScanner._is_loopback_interface(name) for name in pernic
        ):
            return CapabilityState.SUPPORTED
        if stats and any(
            not SystemScanner._is_loopback_interface(name) for name in stats
        ):
            return CapabilityState.SUPPORTED
        if pernic is None and stats is None:
            return CapabilityState.SUPPORTED
        return CapabilityState.UNSUPPORTED

    @staticmethod
    def _rate_pair_text(down_rate: float, up_rate: float) -> tuple[str, str]:
        """Return (download, upload) rate text in one shared unit.

        Both directions use the unit of the larger rate so the two values stay
        even on the card and read as a single line.
        """

        largest = max(down_rate, up_rate)
        scale, unit = SystemScanner._byte_unit(largest)
        return (
            f"{down_rate / scale:.2f} {unit}/s",
            f"{up_rate / scale:.2f} {unit}/s",
        )

    def _sample_network_rates(
        self,
        counters: Any,
    ) -> tuple[float | None, float | None]:
        """Return (download, upload) rates in bytes/sec from counter deltas.

        The first sample has no delta, so it returns ``(None, None)``. Counter
        resets (a smaller reading than the previous one) are clamped to zero
        rather than reported as a negative spurious rate.
        """

        now = time.monotonic()
        sent = counters.bytes_sent
        received = counters.bytes_recv

        with self._network_sample_lock:
            previous = self._network_sample
            self._network_sample = (now, sent, received)
        if previous is None:
            return None, None

        previous_now, previous_sent, previous_received = previous
        elapsed = now - previous_now
        if elapsed <= 0:
            return None, None

        received_delta = max(received - previous_received, 0)
        sent_delta = max(sent - previous_sent, 0)
        return received_delta / elapsed, sent_delta / elapsed

    def _reset_network_sample(self) -> None:
        """Clear the persistent network-rate baseline.

        Used when network polling resumes after a pause so the first resumed
        sample shows ``—`` instead of an average across the whole paused
        interval presented as a current rate.
        """

        with self._network_sample_lock:
            self._network_sample = None

    @staticmethod
    def _is_loopback_interface(name: str) -> bool:
        """Return whether an interface name is the loopback adapter."""

        return name.casefold().startswith("lo")

    @staticmethod
    def _up_interface_names(
        interface_stats: Any,
    ) -> set[str] | None:
        """Return the names of interfaces reported up, or None when unknown.

        ``None`` means the up/down table could not be read; an empty set means
        the table was read and no interface is up.
        """

        if interface_stats is None:
            return None
        return {
            name
            for name, stats in interface_stats.items()
            if getattr(stats, "isup", False)
        }

    @staticmethod
    def _up_interfaces(psutil_module: Any) -> set[str] | None:
        """Return the names of interfaces reported up, or None when unknown.

        Reads the up/down table once via the best-effort boundary, then defers
        to ``_up_interface_names`` so the one-read behaviour is shared with the
        observation-based network card path.
        """

        interface_stats = SystemScanner._psutil_value(
            lambda: psutil_module.net_if_stats()
        )
        return SystemScanner._up_interface_names(interface_stats)

    @staticmethod
    def _active_interface_from_counters(
        per_interface_counters: Any,
        up_interfaces: set[str] | None = None,
    ) -> str | None:
        """Return the busiest up, non-loopback interface, or None.

        Operates purely on already-read per-interface counters and the up/down
        name set so the network card reads each sensor exactly once. ``None``
        ``up_interfaces`` means the up/down table was not read, matching the
        best-effort default of not failing when the table is unavailable.
        """

        if not per_interface_counters:
            return None

        candidates = {
            name: getattr(counters, "bytes_recv", 0)
            + getattr(counters, "bytes_sent", 0)
            for name, counters in per_interface_counters.items()
            if not SystemScanner._is_loopback_interface(name)
            and (up_interfaces is None or name in up_interfaces)
        }
        return (
            max(candidates, key=lambda name: candidates[name]) if candidates else None
        )

    @staticmethod
    def _active_interface(
        psutil_module: Any,
        *,
        up_interfaces: set[str] | None = None,
    ) -> str | None:
        """Return the busiest up, non-loopback interface, or None.

        Interface metadata is best-effort: when per-interface counters or the
        up/down table are unavailable, the card simply omits the interface
        name instead of failing. ``up_interfaces`` may be passed in by the
        caller (already read once) to avoid re-reading the table; ``None``
        means the table was not read here, matching the default behaviour.
        """

        per_nic = SystemScanner._psutil_value(
            lambda: psutil_module.net_io_counters(pernic=True)
        )

        if up_interfaces is None:
            up_interfaces = SystemScanner._up_interfaces(psutil_module)

        return SystemScanner._active_interface_from_counters(per_nic, up_interfaces)

    @staticmethod
    def _vpn_interface_from_names(
        up_interfaces: set[str] | None,
    ) -> str | None:
        """Return an up tunnel/VPN interface name from an up-interface name set.

        Detection is a conservative, generic device-type heuristic (tun, tap,
        utun, ppp, ipsec, wg) over the interface up/down name set; it carries
        no provider-specific assumptions. Shared by the standalone probe and
        the observation-based network card path.
        """

        if not up_interfaces:
            return None

        prefixes = tuple(SystemScanner.TUNNEL_INTERFACE_PREFIXES)
        for name in up_interfaces:
            folded = name.casefold()
            if any(
                folded == prefix or folded.startswith(prefix) for prefix in prefixes
            ):
                return name
        return None

    @classmethod
    def _vpn_interface(
        cls,
        psutil_module: Any,
        *,
        up_interfaces: set[str] | None = None,
    ) -> str | None:
        """Return an up tunnel/VPN interface name, or None.

        ``up_interfaces`` may be passed in by the caller (already read once)
        to avoid re-reading the table; ``None`` means the table was not read
        here, so it is read once from ``psutil_module``.
        """

        if up_interfaces is None:
            up_interfaces = cls._up_interfaces(psutil_module)
        return cls._vpn_interface_from_names(up_interfaces)

    def _battery_resource(
        self,
        battery: Any,
        battery_error: Exception | None,
        temperature_lines: list[str],
        temperature_samples: tuple[TemperatureSample, ...] = (),
    ) -> ResourceSummary:
        if battery is not None:
            subtitle = "Charging" if battery.power_plugged else "Not charging"
            details: list[str] = [
                f"Charge: {battery.percent:.1f}%",
                f"Power: {subtitle}",
            ]
            remaining = self._battery_time_remaining(battery)
            if remaining is not None:
                details.append(f"Time remaining: {remaining}")
            if temperature_lines:
                details.extend(temperature_lines)
            return ResourceSummary(
                key="battery",
                title="Battery",
                value=f"{battery.percent:.0f}%",
                subtitle=subtitle,
                percent=battery.percent,
                details=tuple(details),
                capability=CapabilityState.SUPPORTED,
                temperatures=temperature_samples,
            )

        if battery_error is not None:
            return ResourceSummary(
                key="battery",
                title="Battery",
                value="Unavailable",
                subtitle="Battery unavailable",
                percent=None,
                details=("Battery information is unavailable.",),
                failed=True,
                capability=CapabilityState.UNKNOWN,
                temperatures=temperature_samples,
            )

        if temperature_lines:
            return ResourceSummary(
                key="battery",
                title="Battery",
                value="No battery",
                subtitle="Not present on this system",
                percent=None,
                details=tuple(temperature_lines),
                capability=CapabilityState.UNSUPPORTED,
                temperatures=temperature_samples,
            )
        return ResourceSummary(
            key="battery",
            title="Battery",
            value="No battery",
            subtitle="Not present on this system",
            percent=None,
            details=("No temperature sensors detected.",),
            capability=CapabilityState.UNSUPPORTED,
            temperatures=temperature_samples,
        )

    @staticmethod
    def _temperature_value(
        temperature_lines: list[str],
        category: str,
    ) -> str | None:
        """Return one category's temperature suffix (e.g. ``"49°C"``) or None."""

        return detail_line_suffix(temperature_lines, f"{category}: ")

    @staticmethod
    def _battery_time_remaining(battery: Any) -> str | None:
        """Return a human time-left suffix for a discharging battery, or None.

        psutil reports ``secsleft`` only on real battery objects; missing,
        infinite, and non-positive values are treated as unknown so no
        fabricated estimate ever reaches the card.
        """

        if getattr(battery, "power_plugged", True):
            return None
        secsleft = getattr(battery, "secsleft", None)
        if not isinstance(secsleft, (int, float)) or not math.isfinite(secsleft):
            return None
        if secsleft <= 0:
            return None
        minutes = int(secsleft // 60) + 1
        return f"~{minutes // 60}h {minutes % 60:02d}m"

    @staticmethod
    def _read_battery(psutil_module: Any) -> tuple[Any, Exception | None]:
        """Return the battery reading and any error, keeping them distinct.

        `sensors_battery()` returns `None` when no battery is present and
        raises when the reading itself failed, so the card can tell "no
        battery" apart from "temporarily unreadable".
        """

        try:
            return psutil_module.sensors_battery(), None
        except Exception as error:  # noqa: BLE001 - battery is best-effort.
            LOGGER.warning("Battery read failed: %s", error)
            return None, error

    def _cached_temperature_lines(self, psutil_module: Any) -> list[str]:
        """Return temperature lines, re-read at most every refresh window.

        Temperature reads cost a few milliseconds, so per-component refreshes
        (e.g. CPU at ~1s) reuse this cached copy until it is older than
        `TEMPERATURE_REFRESH_SECONDS` instead of hammering the sensor.
        """

        return list(self._cached_temperature_scan(psutil_module).lines)

    def _cached_temperature_scan(self, psutil_module: Any) -> TemperatureScan:
        return self._ttl_cached_value(
            lock=self._temperature_cache_lock,
            cache_name="_temperature_cache",
            ttl_seconds=self.TEMPERATURE_REFRESH_SECONDS,
            loader=lambda: self._temperature_scan(psutil_module),
        )

    @classmethod
    def _temperature_scan(cls, psutil_module: Any) -> TemperatureScan:
        """Return normalised temperature samples plus the concise card lines."""

        sensors = cls._psutil_value(lambda: psutil_module.sensors_temperatures())
        if not isinstance(sensors, dict) or not sensors:
            now = datetime.now(timezone.utc).astimezone()
            return TemperatureScan(now, time.monotonic(), (), ())

        captured_at = datetime.now(timezone.utc).astimezone()
        captured_monotonic = time.monotonic()
        component_map: dict[str, tuple[str, tuple[str, ...]]] = {
            "cpu": ("CPU", cls.CPU_TEMP_DRIVERS),
            "gpu": ("GPU", cls.GPU_TEMP_DRIVERS),
            "storage": ("NVMe", cls.NVME_TEMP_DRIVERS),
        }
        lines: list[str] = []
        grouped: list[tuple[str, tuple[TemperatureSample, ...]]] = []

        for component, (label, drivers) in component_map.items():
            readings: list[TemperatureSample] = []
            for name, entries in sensors.items():
                if not any(driver in name.casefold() for driver in drivers):
                    continue
                if not isinstance(entries, (list, tuple)):
                    continue
                for index, entry in enumerate(entries):
                    current = getattr(entry, "current", None)
                    if not cls._sensible_temperature(current):
                        continue
                    sensor_name = str(
                        getattr(entry, "label", None)
                        or getattr(entry, "sensor", None)
                        or name
                    )
                    sensor_id = f"{name}:{index}:{sensor_name}"
                    readings.append(
                        TemperatureSample(
                            component=component,
                            sensor_id=sensor_id,
                            sensor_name=sensor_name,
                            value_celsius=float(current),
                            sampled_at=captured_at,
                            sampled_monotonic=captured_monotonic,
                        )
                    )
            if readings:
                grouped.append((component, tuple(readings)))
                lines.append(
                    f"{label}: {max(sample.value_celsius for sample in readings):.0f}°C"
                )

        return TemperatureScan(
            captured_at, captured_monotonic, tuple(lines), tuple(grouped)
        )

    @classmethod
    def _temperature_lines(cls, psutil_module: Any) -> list[str]:
        """Return the legacy concise temperature lines for compatibility tests."""

        return list(cls._temperature_scan(psutil_module).lines)

    @staticmethod
    def _sensible_temperature(value: Any) -> TypeGuard[int | float]:
        return isinstance(value, (int, float)) and 0 < value < 250

    def scan_processes(
        self,
        cancel_event: threading.Event | None = None,
    ) -> list[ProcessCandidate]:
        self._check_cancelled(cancel_event)
        psutil_module = self._require_psutil()
        current_user = getpass.getuser()
        protected_pids = self._protected_pids()
        processes = list(self._process_iter(attrs=["pid", "create_time"]))
        process_creation_times: dict[int, float] = {}
        for process in processes:
            self._check_cancelled(cancel_event)
            try:
                create_time = process.info.get("create_time")
                if isinstance(create_time, (int, float)):
                    process_creation_times[process.pid] = float(create_time)
            except (AttributeError, KeyError, TypeError):
                continue

        for process in processes:
            self._check_cancelled(cancel_event)
            try:
                process.cpu_percent(None)
            except (psutil_module.NoSuchProcess, psutil_module.AccessDenied):
                continue

        if cancel_event is not None:
            if cancel_event.wait(self.PROCESS_SAMPLE_SECONDS):
                raise ScanCancelled("Process scan cancelled")
        else:
            time.sleep(self.PROCESS_SAMPLE_SECONDS)

        candidates: list[ProcessCandidate] = []

        for process in processes:
            self._check_cancelled(cancel_event)
            try:
                info = process.as_dict(
                    attrs=[
                        "pid",
                        "name",
                        "username",
                        "memory_info",
                        "memory_percent",
                        "create_time",
                    ]
                )
                cpu_percent = process.cpu_percent(None)
                memory_info = info["memory_info"]
                memory_bytes = memory_info.rss
                memory_percent = info["memory_percent"]
                expected_create_time = process_creation_times.get(info["pid"])
                current_create_time = info.get("create_time")
                if expected_create_time is None or not isinstance(
                    current_create_time,
                    (int, float),
                ):
                    continue
                if float(current_create_time) != expected_create_time:
                    continue
                self._check_cancelled(cancel_event)
            except (
                psutil_module.NoSuchProcess,
                psutil_module.AccessDenied,
                AttributeError,
                KeyError,
                TypeError,
            ):
                continue

            if memory_bytes < self.PROCESS_MIN_BYTES and cpu_percent < 1:
                continue

            name = info["name"] or f"Process {info['pid']}"
            username = info["username"] or "Unknown"
            protected_name = is_protected_process_name(
                name, self.PROTECTED_PROCESS_NAMES
            )
            action_allowed = (
                self._same_user(username, current_user)
                and info["pid"] not in protected_pids
                and not protected_name
            )
            activity = self._activity_label(cpu_percent)

            candidates.append(
                ProcessCandidate(
                    pid=info["pid"],
                    name=name,
                    memory_bytes=memory_bytes,
                    memory_percent=memory_percent,
                    cpu_percent=cpu_percent,
                    activity=activity,
                    username=username,
                    action_allowed=action_allowed,
                    create_time=float(current_create_time),
                )
            )

        return candidates

    @staticmethod
    def _activity_label(cpu_percent: float) -> str:
        """Classify a process as Active or Low activity from its delta sample.

        The classification threshold is deliberately small so near-idle
        processes are not shown as busy, and the value passed in is already a
        delta over `PROCESS_SAMPLE_SECONDS` (never a single instantaneous
        reading).
        """

        if cpu_percent < SystemScanner.PROCESS_ACTIVITY_MIN_CPU_PERCENT:
            return "Low activity"
        return "Active"

    @staticmethod
    def _process_iter(*, attrs: list[str]) -> Any:
        psutil_module = SystemScanner._require_psutil()
        try:
            return psutil_module.process_iter(attrs=attrs)
        except TypeError:
            return psutil_module.process_iter()

    def scan_downloads(
        self,
        progress_callback: ProgressCallback | None = None,
        cancel_event: threading.Event | None = None,
    ) -> list[FileCandidate]:
        return self._sync_download_scanner().scan_downloads(
            progress_callback=progress_callback,
            cancel_event=cancel_event,
        )

    def _download_file_stats(
        self,
        root: Path,
        progress_callback: ProgressCallback | None = None,
        cancel_event: threading.Event | None = None,
    ) -> dict[Path, os.stat_result]:
        return self._sync_download_scanner()._download_file_stats(
            root,
            progress_callback=progress_callback,
            cancel_event=cancel_event,
        )

    def trash_size(self) -> int:
        if platform.system() == "Windows":
            return self._windows_trash_size()

        total = 0
        for trash in self._trash_paths():
            if not trash.exists():
                continue
            total += self._directory_file_size(trash)
        return total

    @staticmethod
    def _directory_file_size(root: Path) -> int:
        total = 0
        for entry in walk_directory_entries(root, skip_dotfiles=False):
            try:
                total += entry.stat(follow_symlinks=False).st_size
            except OSError:
                continue
        return total

    @staticmethod
    def _windows_trash_size() -> int:
        windll = windows_windll()
        try:
            shell32 = windll.shell32 if windll is not None else None
            query_recycle_bin = (
                shell32.SHQueryRecycleBinW if shell32 is not None else None
            )
        except (AttributeError, OSError, ctypes.ArgumentError):
            return 0
        if query_recycle_bin is None:
            return 0

        info = _RecycleBinInfo()
        info.cb_size = ctypes.sizeof(info)
        try:
            query_recycle_bin.argtypes = [
                ctypes.c_wchar_p,
                ctypes.POINTER(_RecycleBinInfo),
            ]
            query_recycle_bin.restype = ctypes.c_long
            result = query_recycle_bin(None, ctypes.byref(info))
        except (OSError, TypeError, AttributeError, ctypes.ArgumentError):
            return 0

        if result != 0 or info.size < 0:
            return 0
        return int(info.size)

    def _protected_pids(self) -> set[int]:
        return protected_process_pids(psutil)

    @classmethod
    def _file_hash(
        cls,
        path: Path,
        cancel_event: threading.Event | None = None,
    ) -> str:
        return file_sha256(
            path,
            chunk_bytes=cls.HASH_CHUNK_BYTES,
            cancel_event=cancel_event,
        )

    @staticmethod
    def _check_cancelled(cancel_event: threading.Event | None) -> None:
        check_cancelled(cancel_event)

    @staticmethod
    def _hash_fingerprint(stat: os.stat_result) -> HashFingerprint:
        return stat_fingerprint(stat)

    def _file_content_marker(
        self,
        path: Path,
        cancel_event: threading.Event | None = None,
    ) -> bytes:
        """Validate the complete file content before reusing a digest."""
        return file_content_marker(
            path,
            chunk_bytes=self.HASH_CHUNK_BYTES,
            cancel_event=cancel_event,
        )

    def gpu_details(self) -> tuple[str, ...]:
        """Return platform-appropriate GPU details within a bounded time.

        Kept as the tuple-returning compatibility surface; the structured
        capability-aware probe lives in `_gpu_probe`, which this delegates to.
        """

        return self._gpu_probe().details

    def _gpu_probe(self) -> GpuProbe:
        """Return GPU details and typed capability within a bounded time.

        GPU detection can call pynvml, which cannot be interrupted in-process,
        so the detection runs on a short-lived worker that is joined with a
        timeout. The query lifecycle is guarded by one lock and a generation
        counter, so concurrent calls (full scan plus component refresh) can
        never start duplicate probes, a late worker can never clear a newer
        query's state, and `_stop_gpu_query` can abandon an in-flight worker.

        While a previous worker is still running (hung or slower than the
        budget), later calls return the timeout message immediately so a
        wedged driver cannot stack up one blocked worker per scan. A worker
        that eventually finishes clears the state, so a merely slow query
        recovers on the next scan; a query that is still hung after
        `GPU_QUERY_ABANDON_SECONDS` is abandoned on the next call so GPU
        reporting always recovers.
        """

        with self._gpu_query_lock:
            if self._gpu_query_in_flight:
                timed_out_at = self._gpu_query_timed_out_at
                if (
                    timed_out_at is not None
                    and time.monotonic() - timed_out_at
                    >= self.GPU_QUERY_ABANDON_SECONDS
                ):
                    self._gpu_query_generation += 1
                    self._gpu_query_in_flight = False
                    self._gpu_query_timed_out_at = None
                    LOGGER.warning("Abandoning wedged GPU query and restarting")
                else:
                    probe = GpuProbe(
                        (self.GPU_QUERY_TIMEOUT_MESSAGE,),
                        CapabilityState.UNKNOWN,
                    )
                    self._remember_gpu_capability(probe.capability)
                    return probe

            generation = self._gpu_query_generation
            results: list[GpuProbe] = []

            def detect() -> None:
                try:
                    results.append(self._make_gpu_detector().detect_with_capability())
                except Exception as error:  # noqa: BLE001 - GPU queries must not raise.
                    results.append(
                        GpuProbe(
                            (gpu_unavailable_message(error),),
                            CapabilityState.UNKNOWN,
                        )
                    )
                finally:
                    with self._gpu_query_lock:
                        if self._gpu_query_generation == generation:
                            self._gpu_query_in_flight = False
                            self._gpu_query_timed_out_at = None

            worker = threading.Thread(target=detect, daemon=True)
            try:
                self._gpu_query_in_flight = True
                worker.start()
            except RuntimeError as error:
                self._gpu_query_in_flight = False
                probe = GpuProbe(
                    (gpu_unavailable_message(error),),
                    CapabilityState.UNKNOWN,
                )
                self._remember_gpu_capability(probe.capability)
                return probe

        worker.join(self.GPU_QUERY_TIMEOUT_SECONDS)
        if worker.is_alive():
            with self._gpu_query_lock:
                self._gpu_query_timed_out_at = time.monotonic()
            probe = GpuProbe(
                (self.GPU_QUERY_TIMEOUT_MESSAGE,),
                CapabilityState.UNKNOWN,
            )
        else:
            probe = (
                results[0]
                if results
                else GpuProbe(
                    (self.GPU_QUERY_TIMEOUT_MESSAGE,),
                    CapabilityState.UNKNOWN,
                )
            )
        self._remember_gpu_capability(probe.capability)
        return probe

    def _remember_gpu_capability(self, capability: CapabilityState) -> None:
        """Record the calling thread's GPU capability for its own scan.

        ``scan_component`` calls ``gpu_details()`` for the tuple and reads the
        capability back here on the same thread; when ``gpu_details`` is
        monkeypatched (no probe ran) no entry exists and ``UNKNOWN`` is used.
        Each thread only writes and later reads its own key, so the dict
        needs no lock (and must not re-enter ``_gpu_query_lock``).
        """

        self._gpu_capabilities_by_thread[threading.get_ident()] = capability

    def _gpu_capability_for_thread(self) -> CapabilityState:
        return self._gpu_capabilities_by_thread.pop(
            threading.get_ident(),
            CapabilityState.UNKNOWN,
        )

    def _make_gpu_detector(self) -> GpuDetector:
        return GpuDetector(
            system=platform.system,
            nvidia_loader=self._nvidia_gpu_probe,
            mac_loader=lambda: self._cached_static_gpu_probe(self._mac_gpu_probe),
            windows_loader=lambda: self._cached_static_gpu_probe(
                self._windows_gpu_probe
            ),
            linux_loader=lambda: self._cached_static_gpu_probe(self._linux_gpu_probe),
        )

    def _cached_static_gpu_probe(
        self,
        loader: Callable[[], GpuProbe],
    ) -> GpuProbe:
        return self._cached_fingerprint_value(
            lock=self._static_gpu_lock,
            value_name="_static_gpu_details",
            fingerprint_name="_static_gpu_fingerprint",
            fingerprint=self._static_fingerprint(),
            loader=loader,
            acceptable=lambda probe: probe.capability == CapabilityState.SUPPORTED,
        )

    def _nvidia_gpu_probe(self) -> GpuProbe | None:
        """Return the NVIDIA probe, or None when NVIDIA is unavailable."""

        details = self._nvidia_gpu_details()
        if details is None:
            return None
        return GpuProbe(details, CapabilityState.SUPPORTED)

    def _nvidia_gpu_details(self) -> tuple[str, ...] | None:
        """Return NVIDIA GPU detail lines, or None when unavailable.

        A failed NVML probe is remembered per scanner so hosts without the
        NVML shared library do not re-attempt (and re-log) the failed
        ``nvmlInit`` on every scan; `reset_static_cache()` re-enables the
        probe. Successful probes are never remembered, so NVIDIA-capable
        hosts still query every scan exactly as before.
        """

        if pynvml is None:
            return None

        if self._nvml_probe_failed:
            return None

        try:
            pynvml.nvmlInit()
            lines: list[str] = []
            for (
                name,
                memory_used,
                memory_total,
                usage_gpu,
                _temperature,
            ) in nvidia_device_readings(
                pynvml,
                include_temperature=False,
            ):
                lines.extend(
                    [
                        name,
                        f"GPU usage: {usage_gpu}%",
                        (
                            f"Memory: {self.format_bytes(memory_used)} used of "
                            f"{self.format_bytes(memory_total)}"
                        ),
                    ]
                )
            return tuple(lines) or None
        except Exception as error:  # noqa: BLE001 - NVIDIA queries are best-effort text.
            LOGGER.warning("NVIDIA GPU query failed: %s", error)
            with self._static_gpu_lock:
                self._nvml_probe_failed = True
            return None
        finally:
            with contextlib.suppress(Exception):
                pynvml.nvmlShutdown()

    @staticmethod
    def _mac_gpu_read() -> tuple[tuple[str, ...], str | None]:
        payload, error = run_json_command(
            ["system_profiler", "SPDisplaysDataType", "-json"],
            timeout_seconds=SystemScanner.GPU_COMMAND_TIMEOUT_SECONDS,
            runner=subprocess.run,
        )
        if error is not None:
            return (), error

        displays = payload.get("SPDisplaysDataType", [])
        lines: list[str] = []
        for display in displays:
            name = display.get("sppci_model") or display.get("_name") or "Apple GPU"
            lines.append(str(name))
            if memory := display.get("spdisplays_vram"):
                lines.append(f"Memory: {memory}")
            if metal := display.get("spdisplays_metal"):
                lines.append(f"Metal: {metal}")
        return tuple(lines), None

    @classmethod
    def _mac_gpu_details(cls) -> tuple[str, ...]:
        return cls._mac_gpu_probe().details

    @classmethod
    def _mac_gpu_probe(cls) -> GpuProbe:
        return gpu_probe_from_read(cls._mac_gpu_read)

    @classmethod
    def _windows_gpu_read(cls) -> tuple[tuple[str, ...], str | None]:
        command = (
            "Get-CimInstance Win32_VideoController | "
            "Select-Object Name,AdapterRAM,DriverVersion | ConvertTo-Json"
        )
        controllers, error = run_json_command(
            ["powershell", "-NoProfile", "-Command", command],
            timeout_seconds=SystemScanner.GPU_COMMAND_TIMEOUT_SECONDS,
            runner=subprocess.run,
            empty_stdout_fallback="[]",
        )
        if error is not None:
            return (), error

        if isinstance(controllers, dict):
            controllers = [controllers]

        lines: list[str] = []
        for controller in controllers:
            name = controller.get("Name") or "Windows GPU"
            lines.append(str(name))
            adapter_ram = controller.get("AdapterRAM")
            if isinstance(adapter_ram, int) and adapter_ram > 0:
                lines.append(f"Memory: {cls.format_bytes(adapter_ram)}")
            if driver := controller.get("DriverVersion"):
                lines.append(f"Driver: {driver}")
        return tuple(lines), None

    @classmethod
    def _windows_gpu_details(cls) -> tuple[str, ...]:
        return cls._windows_gpu_probe().details

    @classmethod
    def _windows_gpu_probe(cls) -> GpuProbe:
        return gpu_probe_from_read(cls._windows_gpu_read)

    @staticmethod
    def _linux_gpu_read() -> tuple[tuple[str, ...], str | None]:
        stdout, error = run_text_command(
            ["lspci"],
            timeout_seconds=SystemScanner.GPU_COMMAND_TIMEOUT_SECONDS,
            runner=subprocess.run,
        )
        if error is not None:
            return (), error

        gpu_lines = [
            line.split(": ", 1)[-1]
            for line in stdout.splitlines()
            if "VGA compatible controller" in line
            or "3D controller" in line
            or "Display controller" in line
        ]
        return tuple(gpu_lines), None

    @classmethod
    def _linux_gpu_details(cls) -> tuple[str, ...]:
        return cls._linux_gpu_probe().details

    @classmethod
    def _linux_gpu_probe(cls) -> GpuProbe:
        return gpu_probe_from_read(cls._linux_gpu_read)

    @classmethod
    def _default_downloads_path(cls) -> Path:
        return cls._make_downloads_path_resolver().select()

    @staticmethod
    def _is_directory(path: Path) -> bool:
        return DownloadsPathResolver._is_directory(path)

    @staticmethod
    def _safe_downloads_fallback(home: Path) -> Path:
        return DownloadsPathResolver._safe_downloads_fallback(home)

    @staticmethod
    def _path_exists(path: Path) -> bool:
        return DownloadsPathResolver._path_exists(path)

    @staticmethod
    def _windows_downloads_path() -> Path | None:
        return DownloadsPathResolver._windows_downloads_path()

    @staticmethod
    def _trash_paths() -> tuple[Path, ...]:
        system = platform.system()
        if system == "Darwin":
            return (Path.home() / ".Trash",)
        if system == "Linux":
            return (Path.home() / ".local" / "share" / "Trash" / "files",)
        return ()

    @staticmethod
    def _same_user(username: str, current_user: str) -> bool:
        return usernames_match(username, current_user)
