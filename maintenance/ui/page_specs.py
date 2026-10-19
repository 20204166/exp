"""Toolkit-neutral value contracts shared by page-data projections and views."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DiscoveredPeerSpec:
    """Presentation data for one discovered (untrusted) peer."""

    node_id: str
    hostname: str
    app_version: str
    compatible: bool
    connectable: bool
    port: int | None
    identity_fingerprint: str | None = None
    transport_fingerprint: str | None = None
    pairing_state: str = "discovered"
    has_pair_relationship: bool = False


@dataclass(frozen=True, slots=True)
class LocalClusterSpec:
    """Local machine's cluster membership and dashboard-sharing status."""

    joined: bool
    local_role: str
    coordinator_node_id: str | None
    coordinator_display_name: str | None
    coordinator_status: str
    dashboard_share_active: bool
    dashboard_share_expires_at: float
    has_peer_grants: bool
    coordinator_lease_expires_at: float = 0.0
    coordinator_lease_healthy: bool = False


@dataclass(frozen=True, slots=True)
class TrustedNodeSpec:
    """Presentation data for one trusted/authorised node."""

    node_id: str
    display_name: str
    hostname: str
    color: str | None
    status: str
    host: str
    port: int | None
    selectable: bool
    openable: bool = False
    is_manual: bool = False
    identity_fingerprint: str | None = None
    identity_status: str = "unverified"
    permissions: tuple[str, ...] = ()
    pairing_state: str = "trusted"
    target_state: str = "Unknown"
    role: str = "worker"
    roles: tuple[str, ...] = ()
    role_editable: bool = False
    paused: bool = False
    has_active_job: bool = False
    connection_status: str = "unknown"
    manual_disconnected: bool = False
    retry_automatic: bool = True
    is_cluster_member: bool = False


@dataclass(frozen=True, slots=True)
class ClusterNodeSpec:
    """Presentation data for one machine on the All Systems overview."""

    node_id: str
    display_name: str
    hostname: str
    color: str | None
    trust: str
    status: str
    capabilities: tuple[str, ...]
    is_local: bool
    selectable: bool
    last_refresh: str | None = None
    pairing_state: str = "trusted"
    target_state: str = "Unknown"
    role: str = "worker"
    paused: bool = False
    role_editable: bool = False
    has_active_job: bool = False
    share_active: bool = False
    is_cluster_member: bool = False


@dataclass(frozen=True, slots=True)
class SettingsCategorySpec:
    """Presentation data for one navigation card on the Settings hub."""

    key: str
    title: str
    description: str


@dataclass(frozen=True, slots=True)
class IntervalControlSpec:
    """Presentation data for one interval control (values in whole seconds)."""

    key: str
    title: str
    seconds: int
    minimum_seconds: int
    maximum_seconds: int
    step_seconds: int


@dataclass(frozen=True, slots=True)
class CardControlSpec:
    """Presentation data for one card visibility control."""

    key: str
    title: str
    enabled: bool
