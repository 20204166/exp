import gc
import os
import platform
import time
from datetime import datetime

try:
    import psutil
except ImportError:
    psutil = None

try:
    import pynvml
except ImportError:
    pynvml = None


class Analyzer:
    """Analyse system resources and run a controlled RAM experiment."""

    BYTES_IN_GIB = 1024**3

    def __init__(
        self,
        memory_test_percent: float = 1.0,
        max_memory_test_gib: float = 1.0,
    ) -> None:
        if not 0 < memory_test_percent <= 5:
            raise ValueError("memory_test_percent must be between 0 and 5.")

        if max_memory_test_gib <= 0:
            raise ValueError("max_memory_test_gib must be greater than 0.")

        self.memory_test_percent = memory_test_percent
        self.max_memory_test_bytes = int(
            max_memory_test_gib * self.BYTES_IN_GIB
        )

    @staticmethod
    def _require_psutil() -> None:
        if psutil is None:
            raise RuntimeError(
                "psutil is not installed. Run: python -m pip install psutil"
            )

    @classmethod
    def _format_bytes(cls, number_of_bytes: int | float) -> str:
        return f"{number_of_bytes / cls.BYTES_IN_GIB:.2f} GiB"

    def system_info(self) -> list[str]:
        """Return operating-system and uptime information."""
        self._require_psutil()

        boot_time = datetime.fromtimestamp(psutil.boot_time())

        return [
            f"Operating system: {platform.system()} {platform.release()}",
            f"Machine: {platform.machine()}",
            f"Processor: {platform.processor() or 'Unknown'}",
            f"Boot time: {boot_time:%Y-%m-%d %H:%M:%S}",
        ]

    def cpu_info(self) -> list[str]:
        """Return CPU usage, core-count, and frequency information."""
        self._require_psutil()

        frequency = psutil.cpu_freq()
        frequency_text = (
            f"{frequency.current:.0f} MHz" if frequency else "Unavailable"
        )

        return [
            f"CPU usage: {psutil.cpu_percent(interval=0.4):.1f}%",
            f"Physical cores: {psutil.cpu_count(logical=False) or 'Unknown'}",
            f"Logical cores: {psutil.cpu_count(logical=True) or 'Unknown'}",
            f"Current frequency: {frequency_text}",
        ]

    def memory_info(self) -> list[str]:
        """Return RAM and swap usage information."""
        self._require_psutil()

        memory = psutil.virtual_memory()
        swap = psutil.swap_memory()

        return [
            f"RAM total: {self._format_bytes(memory.total)}",
            f"RAM used: {self._format_bytes(memory.used)} ({memory.percent:.1f}%)",
            f"RAM available: {self._format_bytes(memory.available)}",
            f"Swap total: {self._format_bytes(swap.total)}",
            f"Swap used: {self._format_bytes(swap.used)} ({swap.percent:.1f}%)",
        ]

    def storage_info(self) -> list[str]:
        """Return usage information for accessible storage partitions."""
        self._require_psutil()

        lines: list[str] = []
        checked_mounts: set[str] = set()

        for partition in psutil.disk_partitions(all=False):
            if partition.mountpoint in checked_mounts:
                continue

            checked_mounts.add(partition.mountpoint)

            try:
                usage = psutil.disk_usage(partition.mountpoint)
            except (OSError, PermissionError):
                continue

            name = partition.device or partition.mountpoint
            lines.append(
                f"{name} ({partition.mountpoint}): "
                f"{self._format_bytes(usage.used)} used, "
                f"{self._format_bytes(usage.free)} free, "
                f"{usage.percent:.1f}% full"
            )

        return lines or ["No accessible storage partitions were found."]

    def gpu_info(self) -> list[str]:
        """Return NVIDIA GPU information when NVIDIA monitoring is available."""
        if pynvml is None:
            return [
                "GPU details unavailable. For NVIDIA GPUs, run: "
                "python -m pip install nvidia-ml-py"
            ]

        try:
            pynvml.nvmlInit()
            device_count = pynvml.nvmlDeviceGetCount()
            lines: list[str] = []

            for index in range(device_count):
                handle = pynvml.nvmlDeviceGetHandleByIndex(index)
                name = pynvml.nvmlDeviceGetName(handle)
                memory = pynvml.nvmlDeviceGetMemoryInfo(handle)
                utilisation = pynvml.nvmlDeviceGetUtilizationRates(handle)
                temperature = pynvml.nvmlDeviceGetTemperature(
                    handle,
                    pynvml.NVML_TEMPERATURE_GPU,
                )

                if isinstance(name, bytes):
                    name = name.decode(errors="replace")

                lines.extend(
                    [
                        f"GPU {index}: {name}",
                        f"GPU usage: {utilisation.gpu}%",
                        f"GPU memory used: {self._format_bytes(memory.used)} "
                        f"of {self._format_bytes(memory.total)}",
                        f"GPU temperature: {temperature}°C",
                    ]
                )

            return lines or ["No NVIDIA GPU was detected."]
        except Exception as error:
            return [f"GPU details unavailable: {error}"]
        finally:
            try:
                pynvml.nvmlShutdown()
            except Exception:
                pass

    def network_info(self) -> list[str]:
        """Return total network traffic since the computer started."""
        self._require_psutil()

        network = psutil.net_io_counters()

        return [
            f"Data sent: {self._format_bytes(network.bytes_sent)}",
            f"Data received: {self._format_bytes(network.bytes_recv)}",
        ]

    def battery_info(self) -> list[str]:
        """Return battery information when the machine has a battery."""
        self._require_psutil()

        battery = psutil.sensors_battery()
        if battery is None:
            return ["Battery information is unavailable."]

        power_state = "charging" if battery.power_plugged else "not charging"
        return [f"Battery: {battery.percent:.1f}% ({power_state})"]

    def full_report(self) -> str:
        """Combine every supported system analysis into one report."""
        sections = [
            ("SYSTEM", self.system_info()),
            ("CPU", self.cpu_info()),
            ("RAM AND SWAP", self.memory_info()),
            ("STORAGE", self.storage_info()),
            ("GPU", self.gpu_info()),
            ("NETWORK", self.network_info()),
            ("BATTERY", self.battery_info()),
        ]

        report: list[str] = []
        for title, lines in sections:
            report.append(title)
            report.extend(lines)
            report.append("")

        return "\n".join(report).rstrip()

    def test_memory(self, hold_seconds: float = 2.0) -> str:
        """Temporarily allocate part of available RAM, then release it."""
        self._require_psutil()

        before = psutil.virtual_memory()
        requested_bytes = int(
            before.available * (self.memory_test_percent / 100)
        )
        allocation_bytes = min(
            requested_bytes,
            self.max_memory_test_bytes,
        )
        was_capped = allocation_bytes < requested_bytes
        memory_block: bytearray | None = None

        try:
            memory_block = bytearray(allocation_bytes)

            # Touch one byte per memory page so the operating system commits it.
            for position in range(0, allocation_bytes, 4096):
                memory_block[position] = 1

            during = psutil.virtual_memory()
            time.sleep(hold_seconds)
        except MemoryError:
            return "The system refused the RAM allocation. No memory was kept."
        finally:
            del memory_block
            gc.collect()

        time.sleep(0.2)
        after = psutil.virtual_memory()
        cap_note = " (limited by the 1 GiB safety cap)" if was_capped else ""

        return "\n".join(
            [
                "RAM TEST COMPLETE",
                f"Requested: {self.memory_test_percent:.1f}% of available RAM",
                f"Temporarily allocated: {self._format_bytes(allocation_bytes)}{cap_note}",
                f"Available before: {self._format_bytes(before.available)}",
                f"Available during: {self._format_bytes(during.available)}",
                f"Available after release: {self._format_bytes(after.available)}",
            ]
        )