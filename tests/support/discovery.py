"""Shared discovery fakes for network discovery and session tests."""

from typing import Any

from maintenance.components.network_discovery import DiscoveryAdvertisement


class FakeBackend:
    """In-memory discovery backend driven by the test."""

    def __init__(self, listener: Any, *, available: bool = True) -> None:
        self.listener = listener
        self.available_flag = available
        self.started = False
        self.stopped = False
        self.last_advertisement: Any = None

    @property
    def available(self) -> bool:
        return self.available_flag

    def start(self, advertisement: DiscoveryAdvertisement) -> None:
        self.started = True
        self.last_advertisement = advertisement

    def stop(self) -> None:
        self.stopped = True

    def add(self, service_name: str, info: Any) -> None:
        self.listener("add", service_name, info)

    def update(self, service_name: str, info: Any) -> None:
        self.listener("update", service_name, info)

    def remove(self, service_name: str) -> None:
        self.listener("remove", service_name, None)


class FakeDiscovery:
    """Configurable fake for the discovery component surface."""

    def __init__(
        self,
        events: list[str] | None = None,
        *,
        available: bool = True,
        fail_next_start: bool = False,
    ) -> None:
        self.events = events
        self.available_flag = available
        self.unavailable_reason_value = None if available else "no transport"
        self.on_event: Any = None
        self.started = False
        self.stopped = False
        self.expiries = 0
        self.fail_next_start = fail_next_start

    @property
    def available(self) -> bool:
        return self.available_flag

    @property
    def unavailable_reason(self) -> str | None:
        return self.unavailable_reason_value

    def start(self) -> bool:
        self.started = True
        if self.events is not None:
            self.events.append("discovery.start")
        if self.fail_next_start:
            self.fail_next_start = False
            return False
        return self.available_flag

    def stop(self) -> None:
        self.stopped = True
        if self.events is not None:
            self.events.append("discovery.stop")

    def expire_stale(self) -> None:
        self.expiries += 1

    def emit(self, kind: str, payload: Any) -> None:
        if self.on_event is not None:
            self.on_event(kind, payload)