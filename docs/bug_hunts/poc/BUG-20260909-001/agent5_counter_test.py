"""Agent 5 read-only evidence probes for BUG-20260909-001."""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from maintenance.actions import ProcessManager
from maintenance.components.network_discovery import (
    DiscoveryAdvertisement,
    NetworkDiscovery,
)
from maintenance.components.scan_support import call_legacy_compatible
from maintenance.components.temperature import (
    TemperatureSample,
    TemperatureSeriesSnapshot,
    TemperatureState,
)
from maintenance.ui.thermal_graph import build_telemetry_graph_layout

ROOT = Path(__file__).resolve().parents[4]


def discovery_race_probe() -> None:
    class Backend:
        available = True

        def __init__(self, listener: Any) -> None:
            self.listener = listener

        def start(self, _advertisement: DiscoveryAdvertisement) -> None:
            return None

        def stop(self) -> None:
            return None

    backend: Backend | None = None

    def factory(listener: Any) -> Backend:
        nonlocal backend
        backend = Backend(listener)
        return backend

    discovery = NetworkDiscovery(
        "local",
        advertisement=DiscoveryAdvertisement("local", "local", "host", "1"),
        backend_factory=cast(Any, factory),
        ttl_seconds=0.0,
    )
    assert discovery.start()
    assert backend is not None
    active_backend = backend
    info = SimpleNamespace(
        properties={b"id": b"peer", b"name": b"peer", b"protocol_version": b"1"},
        addresses=[],
        port=1234,
    )
    errors: list[BaseException] = []

    def updates() -> None:
        try:
            for _ in range(2_000):
                active_backend.listener(
                    "update", "peer._system-analyzer._tcp.local.", info
                )
        except (AttributeError, KeyError, RuntimeError) as error:
            errors.append(error)

    def expiry() -> None:
        try:
            for _ in range(2_000):
                discovery.expire_stale(1.0)
        except (AttributeError, KeyError, RuntimeError) as error:
            errors.append(error)

    first = threading.Thread(target=updates)
    second = threading.Thread(target=expiry)
    first.start()
    second.start()
    first.join()
    second.join()
    assert not errors, errors
    print("1 discovery stress: no exception (race not disproven)")


def source_contract_probes() -> None:
    window = (ROOT / "window.py").read_text()
    nodes_page = (ROOT / "maintenance/ui/nodes_connections.py").read_text()
    persistence = (ROOT / "maintenance/persistence.py").read_text()
    installer = (ROOT / "install/install-online.ps1").read_text()
    assert "permissions=permissions" in window
    assert "registry.set_color(NodeId(node_id), None)" in window
    assert "except UnicodeDecodeError" not in persistence
    assert "port = int(raw_port)" in nodes_page
    assert "--force-reinstall" not in installer
    print("2/3/4/5/9 source contracts: reproduced")


def threshold_probe() -> None:
    snapshot = TemperatureSeriesSnapshot(
        component="cpu",
        title="CPU",
        state=TemperatureState.VALID,
        current_celsius=45.0,
        minimum_celsius=40.0,
        maximum_celsius=45.0,
        warning_celsius=90.0,
        critical_celsius=95.0,
        samples=tuple(
            TemperatureSample(
                component="cpu",
                sensor_id=str(index),
                sensor_name="sensor",
                value_celsius=value,
                sampled_at=datetime.now(timezone.utc),
                sampled_monotonic=float(index),
            )
            for index, value in enumerate((40.0, 45.0))
        ),
        events=(),
    )
    layout = build_telemetry_graph_layout(snapshot, 200, 100)
    assert layout is not None and layout.warning_y is not None
    assert layout.warning_y < layout.top
    print("6 threshold geometry: outside plot")


def legacy_probe() -> None:
    calls: list[str] = []

    def primary() -> None:
        calls.append("primary")
        raise TypeError("unexpected keyword argument 'cancel_event'")

    def fallback() -> None:
        calls.append("fallback")

    call_legacy_compatible(primary, fallback)
    assert calls == ["primary", "fallback"]
    print("7 legacy fallback: repeated side-effect-capable call")


def pid_probe() -> None:
    class FakePsutil:
        class NoSuchProcess(Exception):
            pass

        class AccessDenied(Exception):
            pass

        def __init__(self) -> None:
            self.process = SimpleNamespace(
                pid=77,
                name=lambda: "safe-worker",
                username=lambda: "tester",
                create_time=lambda: 2.0,
                exe=lambda: "/bin/safe-worker",
            )

        def Process(self, _pid: int) -> Any:
            return self.process

        def wait_procs(self, processes: Any, timeout: float) -> tuple[Any, list[Any]]:
            del timeout
            return processes, []

    class ProbeManager(ProcessManager):
        @staticmethod
        def _require_psutil() -> Any:
            return FakePsutil()

        @staticmethod
        def _protected_pids(psutil_module: Any) -> set[int]:
            del psutil_module
            return {0, 1}

    result = ProbeManager().request_quit([77], {77: 1.0})
    assert result.errors == ("PID 77 changed since it was scanned.",)
    print("8 PID reuse check: replacement rejected; TOCTOU gap remains")


def layout_source_probe() -> None:
    source = (ROOT / "maintenance/ui/nodes_connections.py").read_text()
    assert 'holder.pack(side="left"' in source
    assert "width=16" in source
    print("10 manual-host narrow layout: fixed horizontal row observed")


def main() -> None:
    discovery_race_probe()
    source_contract_probes()
    threshold_probe()
    legacy_probe()
    pid_probe()
    layout_source_probe()


if __name__ == "__main__":
    main()
