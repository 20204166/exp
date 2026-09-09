"""Opposing Agent 1 independent edge-case probes for BUG-20260909-001."""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import Any, cast

from maintenance.actions import ProcessManager
from maintenance.components.network_discovery import (
    DiscoveryAdvertisement,
    NetworkDiscovery,
)
from maintenance.components.scan_support import call_cancellable
from maintenance.preferences import PreferencesStore


def discovery_expiry_probe() -> None:
    now = [0.0]

    class Backend:
        available = True

        def __init__(self, listener):
            self.listener = listener

        def start(self, _advertisement: DiscoveryAdvertisement) -> None:
            return None

        def stop(self) -> None:
            return None

    backend = Backend(lambda *_args: None)

    def backend_factory(listener: Any) -> Any:
        backend.listener = listener
        return backend

    discovery = NetworkDiscovery(
        "local",
        advertisement=DiscoveryAdvertisement("local", "local", "host", "1"),
        backend_factory=cast(Any, backend_factory),
        clock=lambda: now[0],
        ttl_seconds=10.0,
    )
    assert discovery.start()
    backend.listener(
        "add",
        "peer._system-analyzer._tcp.local.",
        SimpleNamespace(
            properties={
                b"id": b"peer",
                b"name": b"peer",
                b"protocol_version": b"1",
            },
            addresses=[],
            port=1234,
        ),
    )
    assert len(discovery.peers()) == 1
    discovery.expire_stale(10.0)
    assert len(discovery.peers()) == 1
    discovery.expire_stale(10.1)
    assert not discovery.peers()
    print("discovery expiry: PASS")


def legacy_fallback_probe() -> None:
    calls = []

    def primary():
        calls.append("primary")
        raise TypeError("unexpected keyword argument 'cancel_event'")

    def fallback():
        calls.append("fallback")
        return "legacy result"

    assert call_cancellable(primary, fallback, threading.Event()) == "legacy result"
    assert calls == ["primary", "fallback"]
    print(f"legacy fallback calls: PASS {calls}")


def process_identity_probe() -> None:
    class FakePsutil:
        class NoSuchProcess(Exception):
            pass

        class AccessDenied(Exception):
            pass

        def __init__(self):
            self.process = SimpleNamespace(
                pid=77,
                name=lambda: "safe-worker",
                username=lambda: "tester",
                create_time=lambda: 2.0,
                exe=lambda: "/bin/safe-worker",
            )

        def Process(self, _pid):
            return self.process

        def wait_procs(self, processes, timeout):
            return processes, []

    class ProbeManager(ProcessManager):
        @staticmethod
        def _require_psutil():
            return FakePsutil()

        @staticmethod
        def _protected_pids(psutil_module):
            del psutil_module
            return {0, 1}

    manager = ProbeManager()
    result = manager.request_quit([77], {77: 1.0})
    assert not result.stopped
    assert result.errors == ("PID 77 changed since it was scanned.",)
    print(f"process create-time mismatch: PASS {result.errors}")


def permissions_shape_probe() -> None:
    values = {
        "process_review": False,
        "process_termination": True,
        "process_force_termination": False,
    }
    selected = frozenset(key for key, value in values.items() if value)
    assert selected == frozenset({"process_termination"})
    print(f"permission selection shape: PASS {sorted(selected)}")


def malformed_encoding_probe() -> None:
    with TemporaryDirectory() as directory:
        path = Path(directory) / "preferences.json"
        path.write_bytes(b"\xff")
        try:
            PreferencesStore(path).load()
        except UnicodeDecodeError:
            print("invalid UTF-8 preference load: REPRODUCED")
        else:
            raise AssertionError("invalid UTF-8 unexpectedly returned defaults")


def main() -> None:
    logging.disable(logging.CRITICAL)
    discovery_expiry_probe()
    legacy_fallback_probe()
    process_identity_probe()
    permissions_shape_probe()
    malformed_encoding_probe()


if __name__ == "__main__":
    main()
