"""Toolkit-neutral value and callback contracts for node dialogs."""

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NodeDetailsDialogSpec:
    node_id: str
    display_name: str = ""
    hostname: str = ""
    host: str = ""
    port: int | None = None
    pairing_state: str = ""
    target_state: str = ""
    role: str = ""
    permissions: tuple[str, ...] = ()
    selectable: bool = False
    openable: bool = False
    is_manual: bool = False
    paused: bool = False
    role_editable: bool = False
    has_active_job: bool = False
    identity_status: str = ""
    identity_fingerprint: str | None = None
    transport_fingerprint: str | None = None


@dataclass(frozen=True, slots=True)
class NodeDetailsDialogCallbacks:
    on_open: Callable[[str], None] | None = None
    on_test: Callable[[str], None] | None = None
    on_pause: Callable[[str], None] | None = None
    on_resume: Callable[[str], None] | None = None
    on_revoke: Callable[[str], None] | None = None
    on_remove_connection: Callable[[str], None] | None = None
    on_remove_job: Callable[[str], None] | None = None


@dataclass(frozen=True, slots=True)
class PairingDialogSpec:
    node_id: str
    display_name: str = ""
    identity_fingerprint: str | None = None
    transport_fingerprint: str | None = None


@dataclass(frozen=True, slots=True)
class PairingDialogCallbacks:
    on_pair: Callable[[str], None]


@dataclass(frozen=True, slots=True)
class ConnectionDialogCallbacks:
    on_add: Callable[[str, str, int | None], None] | None = None
    on_test: Callable[[str], None] | None = None


@dataclass(frozen=True, slots=True)
class SharingDialogCallbacks:
    on_share: Callable[[], bool | None]
    on_stop: Callable[[], bool | None]
