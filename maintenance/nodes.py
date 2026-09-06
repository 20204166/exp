"""Node/target model and registry for the System Analyzer cluster boundary.

This module owns the domain concepts behind "selected node": stable identity,
display metadata, trust/capability state, per-node runtime context, and the
central registry that both the local machine and future discovered/paired
peers are registered in. It deliberately imports no Tkinter, scanner, network,
or transport code, so the model is safe to load in any interpreter and inside
tests without a display.

Invariants that every caller must preserve:

- ``DISCOVERED != TRUSTED != AUTHORISED``. A discovered candidate never gains
  read or action capabilities by virtue of being seen on the network.
- The local node is always registered and always selectable.
- Coordinator/cache keys are node-qualified through ``node_operation_key`` so
  two nodes can never overwrite or coalesce each other's work.
- A node without a capability (or whose state is unknown) is refused for that
  action; capability is never inferred from a hostname or from ``is_local``.
"""

import secrets
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

from maintenance.models import DashboardSnapshot

LOCAL_NODE_ID = "local"
LOCAL_NODE_HOSTNAME = "localhost"
LOCAL_DISPLAY_NAME = "This System"
NODE_SNAPSHOT_SCHEMA_VERSION = 1


def generate_node_secret() -> str:
    """Return a fresh 256-bit node credential as hex text.

    The secret authenticates every request this machine sends for one remote
    node; it is generated at pairing time and never travels on the wire.
    """

    return secrets.token_hex(32)


class NodeStatus(str, Enum):
    """Connectivity state of a registered node."""

    ONLINE = "online"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


class NodeTrustState(str, Enum):
    """How a node entered the registry and what may be done with it.

    ``LOCAL`` is the machine this process runs on. ``DISCOVERED``/``UNTRUSTED``
    are network observations that must be explicitly promoted by a future
    pairing flow before they become ``TRUSTED`` (and later ``AUTHORISED``).
    """

    LOCAL = "local"
    DISCOVERED = "discovered"
    UNTRUSTED = "untrusted"
    TRUSTED = "trusted"
    AUTHORISED = "authorised"


class NodeCapability(str, Enum):
    """Capabilities a node advertises or is authorised for.

    Read and destructive capabilities are deliberately separate: a node may
    support process review while explicitly refusing termination, and a remote
    node defaults to read-only regardless of what its discovery metadata says.
    """

    DASHBOARD_READ = "dashboard_read"
    COMPONENT_READ = "component_read"
    PROCESS_REVIEW = "process_review"
    PROCESS_TERMINATION = "process_termination"
    PROCESS_FORCE_TERMINATION = "process_force_termination"
    STORAGE_REVIEW = "storage_review"
    CLEANUP = "cleanup"
    REMOTE_MANAGEMENT = "remote_management"


@dataclass(frozen=True, slots=True)
class NodeId:
    """Stable opaque identity for one node.

    Never derived from a display name, hostname, address, or selector position
    so a node's identity survives renames, DHCP churn, and multi-homing.
    """

    value: str

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class NodeDescriptor:
    """Immutable metadata describing one registered node."""

    id: NodeId
    display_name: str
    hostname: str
    is_local: bool
    trust: NodeTrustState
    status: NodeStatus
    capabilities: frozenset[NodeCapability]
    platform: str | None = None
    color: str | None = None

    def has(self, capability: NodeCapability) -> bool:
        return capability in self.capabilities


def is_trusted_descriptor(descriptor: NodeDescriptor) -> bool:
    """Return whether a descriptor is trusted or authorised."""

    return descriptor.trust in (NodeTrustState.TRUSTED, NodeTrustState.AUTHORISED)


@dataclass(frozen=True, slots=True)
class NodeSnapshot:
    """Versioned, node-bound read snapshot for one machine.

    Carries the node identity and trust/capability state alongside the
    dashboard payload so consumers never have to guess which node produced a
    result. ``is_stale`` expresses freshness against a caller-supplied age
    bound so offline/stale presentation stays in one place.
    """

    node_id: NodeId
    display_name: str
    hostname: str
    platform: str | None
    status: NodeStatus
    capabilities: frozenset[NodeCapability]
    scanned_at: datetime
    dashboard: DashboardSnapshot | None = None
    schema_version: int = NODE_SNAPSHOT_SCHEMA_VERSION

    def is_stale(
        self,
        *,
        now: datetime | None = None,
        max_age: timedelta,
    ) -> bool:
        current = datetime.now(timezone.utc).astimezone() if now is None else now
        return current - self.scanned_at > max_age


@dataclass(frozen=True, slots=True)
class NodeCredentials:
    """The shared secret authenticating one remote node's requests.

    ``secret`` is 256-bit hex text generated at pairing time; the replay and
    freshness protections live in the authenticated transport, not here.
    """

    node_id: NodeId
    secret: str
    created_at: float


def local_capabilities() -> frozenset[NodeCapability]:
    """Return the capabilities the local machine is authorised for.

    These mirror what the current local ``ProcessManager``/``FileManager``
    support; the local safety checks inside those managers remain the final
    authority for any destructive operation.
    """

    return frozenset(
        {
            NodeCapability.DASHBOARD_READ,
            NodeCapability.COMPONENT_READ,
            NodeCapability.PROCESS_REVIEW,
            NodeCapability.PROCESS_TERMINATION,
            NodeCapability.PROCESS_FORCE_TERMINATION,
            NodeCapability.STORAGE_REVIEW,
            NodeCapability.CLEANUP,
        }
    )


def local_node_descriptor(
    *,
    hostname: str = LOCAL_NODE_HOSTNAME,
    display_name: str = LOCAL_DISPLAY_NAME,
    platform_name: str | None = None,
) -> NodeDescriptor:
    """Return the canonical descriptor for the local machine."""

    return NodeDescriptor(
        id=NodeId(LOCAL_NODE_ID),
        display_name=display_name,
        hostname=hostname,
        is_local=True,
        trust=NodeTrustState.LOCAL,
        status=NodeStatus.ONLINE,
        capabilities=local_capabilities(),
        platform=platform_name,
    )


def node_operation_key(node_id: NodeId, operation: str) -> str:
    """Return a node-qualified coordinator/cache key for one operation.

    Every shared operation key must flow through here so two nodes can never
    coalesce, overwrite, or subscribe to each other's work on one coordinator.
    """

    return f"node:{node_id.value}:{operation}"


@dataclass(frozen=True, slots=True)
class ProcessRef:
    """A process reference bound to one node.

    The PID is only meaningful inside its own node; the create-time token (when
    available) protects against PID reuse exactly as the local manager does.
    """

    node_id: NodeId
    pid: int
    create_time: float | None = None


@dataclass(frozen=True, slots=True)
class FileRef:
    """A file reference bound to one node."""

    node_id: NodeId
    path: Path
    size_bytes: int | None = None


@dataclass(frozen=True, slots=True)
class DiscoveredNodeCandidate:
    """Normalized network presence observation, never an authorisation.

    Produced by the discovery component and stored by the registry as an
    untrusted candidate. ``connectable`` and ``compatible`` are separate from
    any trust decision: a connectable-looking peer is still not usable until a
    future pairing flow authorises it.
    """

    stable_id: str
    hostname: str
    addresses: tuple[str, ...]
    port: int | None
    service_name: str
    app_version: str
    protocol_version: str
    platform: str | None
    connectable: bool
    compatible: bool
    last_seen: float


@dataclass(frozen=True, slots=True)
class ProcessActionRefusal:
    """Structured refusal for a destructive process action on a node.

    Returned instead of raising so a dialog can present a read-only/refused
    target without pretending the action ran or failing the whole surface.
    """

    reason: str


@dataclass(frozen=True, slots=True)
class FileActionRefusal:
    reason: str


class NodeProvider(Protocol):
    """Read-side contract every node implementation must satisfy.

    ``Analyzer`` is the initial local implementation. A future authenticated
    remote provider implements the same protocol so cards, dialogs, and the
    dashboard never need to know the transport. All methods are read-only;
    mutation lives behind the action backends instead.
    """

    def dashboard_snapshot(
        self,
        cancel_event: Any | None = None,
        progress_callback: Callable[[str], None] | None = None,
    ) -> Any: ...

    def component_summary(
        self,
        key: str,
        cancel_event: Any | None = None,
    ) -> Any: ...

    def process_candidates(
        self,
        cancel_event: Any | None = None,
    ) -> list[Any]: ...

    def storage_candidates(
        self,
        progress_callback: Callable[[str], None] | None = None,
        cancel_event: Any | None = None,
    ) -> list[Any]: ...

    def reset_component_sample(self, key: str) -> None: ...

    def stop_background_workers(self) -> None: ...


class ProcessActionBackend(Protocol):
    """Target-bound interface for process termination.

    Local implementations reuse the existing safety checks unchanged; remote or
    unauthorised targets return a refusal instead of touching local psutil.
    """

    def request_quit(
        self,
        refs: list[ProcessRef],
    ) -> Any: ...

    def force_quit(
        self,
        refs: list[ProcessRef],
    ) -> Any: ...


class FileActionBackend(Protocol):
    def move_to_trash(
        self,
        refs: list[FileRef],
    ) -> Any: ...


@dataclass
class NodeContext:
    """Runtime state owned by one registered node.

    The window keeps its historical attributes (``analyzer``,
    ``process_manager``, ``file_manager``, ``snapshot``, ``_capabilities``,
    ``_component_scheduler``) mirroring the selected context so existing test
    seams and callers keep working; switching nodes re-syncs the mirrors from
    the newly selected context.
    """

    descriptor: NodeDescriptor
    provider: Any
    process_manager: Any
    file_manager: Any
    scheduler: Any
    coordinator: Any
    snapshot: Any | None = None
    capabilities: dict[str, Any] = field(default_factory=dict)
    capability_counts: dict[str, int] = field(default_factory=dict)
    failed_card_counts: dict[str, int] = field(default_factory=dict)
    full_snapshot_applied_at: float | None = None

    @property
    def node_id(self) -> NodeId:
        return self.descriptor.id


class NodeRegistry:
    """Central owner of known nodes, discovered candidates, and the selection.

    Instance-local (never process-global) so different windows can never
    mutate each other's registries. The registry owns descriptors and runtime
    contexts; ``AppWindow`` owns only the UI reactions to selection changes.
    """

    def __init__(self, local_context: NodeContext | None = None) -> None:
        self._contexts: dict[NodeId, NodeContext] = {}
        self._discovered: dict[NodeId, DiscoveredNodeCandidate] = {}
        self._selected_id: NodeId | None = None
        self._local_id: NodeId | None = None
        if local_context is not None:
            self.register_context(local_context)
            self.select(local_context.node_id)

    def register_context(self, context: NodeContext) -> None:
        node_id = context.node_id
        existing = self._contexts.get(node_id)
        if existing is not None:
            if self._is_placeholder(existing) and self._is_operational(context):
                if context.descriptor.is_local or not is_trusted_descriptor(
                    context.descriptor
                ):
                    raise ValueError(
                        "A trusted placeholder must be replaced by a trusted "
                        "or authorised remote context"
                    )
                self._contexts[node_id] = context
                return
            raise ValueError(f"Node already registered: {node_id}")
        if context.descriptor.is_local:
            if self._local_id is not None:
                raise ValueError("A local node is already registered")
            self._local_id = node_id
        self._contexts[node_id] = context

    def local_id(self) -> NodeId | None:
        return self._local_id

    def context(self, node_id: NodeId) -> NodeContext:
        try:
            return self._contexts[node_id]
        except KeyError as error:
            raise KeyError(f"Unknown node: {node_id}") from error

    def contexts(self) -> tuple[NodeContext, ...]:
        return tuple(self._contexts.values())

    def descriptors(self) -> tuple[NodeDescriptor, ...]:
        return tuple(context.descriptor for context in self._contexts.values())

    def selectable_descriptors(self) -> tuple[NodeDescriptor, ...]:
        """Return descriptors the UI may offer as dashboard targets.

        Only the local node and explicitly trusted/authorised nodes are
        selectable; discovered/untrusted candidates are never selectable so
        discovery can never silently widen the actionable surface.
        """

        return tuple(
            context.descriptor
            for context in self._contexts.values()
            if context.descriptor.trust
            in (
                NodeTrustState.LOCAL,
                NodeTrustState.TRUSTED,
                NodeTrustState.AUTHORISED,
            )
            and (context.descriptor.is_local or self._is_operational(context))
        )

    def select(self, node_id: NodeId) -> NodeId:
        if node_id in self._discovered:
            raise ValueError(f"Node is not selectable (not trusted): {node_id}")
        if node_id not in self._contexts:
            raise KeyError(f"Unknown node: {node_id}")
        if node_id not in {item.id for item in self.selectable_descriptors()}:
            raise ValueError(f"Node is not selectable (not trusted): {node_id}")
        self._selected_id = node_id
        return node_id

    @staticmethod
    def _is_operational(context: NodeContext) -> bool:
        """Return whether a context can safely supply dashboard work.

        Trust records may exist before pairing creates a provider. They remain
        registry metadata, not dashboard targets, until a read provider and a
        per-node scheduler have both been attached.
        """

        return context.provider is not None and context.scheduler is not None

    @classmethod
    def _is_placeholder(cls, context: NodeContext) -> bool:
        return not context.descriptor.is_local and not cls._is_operational(context)

    def selected_id(self) -> NodeId:
        if self._selected_id is None:
            raise RuntimeError("No node is selected")
        return self._selected_id

    def selected_context(self) -> NodeContext:
        return self.context(self.selected_id())

    def update_discovered(
        self, candidate: DiscoveredNodeCandidate
    ) -> NodeDescriptor | None:
        """Record one discovered candidate as untrusted, non-selectable.

        Returns the stored descriptor, or ``None`` when the candidate is the
        local node or otherwise rejected. The candidate never gains read or
        action capabilities here; a future pairing flow promotes it.
        """

        if candidate.stable_id == (
            self._local_id.value if self._local_id else LOCAL_NODE_ID
        ):
            return None
        node_id = NodeId(candidate.stable_id)
        known_context = self._contexts.get(node_id)
        if known_context is not None:
            descriptor = known_context.descriptor
            display_name = descriptor.display_name
            if display_name == descriptor.hostname:
                display_name = candidate.hostname
            known_context.descriptor = replace(
                descriptor,
                display_name=display_name,
                hostname=candidate.hostname,
                status=NodeStatus.ONLINE,
                platform=candidate.platform,
            )
            return known_context.descriptor
        self._discovered[node_id] = candidate
        descriptor = NodeDescriptor(
            id=node_id,
            display_name=candidate.hostname,
            hostname=candidate.hostname,
            is_local=False,
            trust=NodeTrustState.UNTRUSTED,
            status=NodeStatus.ONLINE if candidate.last_seen else NodeStatus.UNKNOWN,
            capabilities=frozenset(),
            platform=candidate.platform,
        )
        return descriptor

    def discovered_candidates(self) -> tuple[DiscoveredNodeCandidate, ...]:
        return tuple(self._discovered.values())

    def remove_discovered(self, node_id: NodeId) -> None:
        self._discovered.pop(node_id, None)
        context = self._contexts.get(node_id)
        if context is not None and not context.descriptor.is_local:
            context.descriptor = replace(context.descriptor, status=NodeStatus.OFFLINE)

    def reject_discovered(self, node_id: NodeId) -> None:
        """Explicitly reject one discovered peer candidate."""

        self.remove_discovered(node_id)

    def promote_to_trusted(
        self,
        node_id: NodeId,
        *,
        capabilities: Iterable[NodeCapability] = (),
    ) -> NodeDescriptor:
        """Explicitly promote a discovered node to trusted, read-only.

        A future Nodes & Connections pairing flow calls this after the user
        approves a peer. Defaults to no action capabilities: authorisation is a
        separate, later step and is never granted by discovery.
        """

        candidate = self._discovered.get(node_id)
        if candidate is None:
            raise KeyError(f"No discovered node: {node_id}")
        requested_capabilities = frozenset(capabilities)
        read_capabilities = frozenset(
            {
                NodeCapability.DASHBOARD_READ,
                NodeCapability.COMPONENT_READ,
                NodeCapability.PROCESS_REVIEW,
                NodeCapability.STORAGE_REVIEW,
            }
        )
        if not requested_capabilities <= read_capabilities:
            raise ValueError(
                "Trusted nodes may only receive read capabilities; "
                "authorisation is required for destructive capabilities"
            )
        descriptor = NodeDescriptor(
            id=node_id,
            display_name=candidate.hostname,
            hostname=candidate.hostname,
            is_local=False,
            trust=NodeTrustState.TRUSTED,
            status=NodeStatus.ONLINE,
            capabilities=frozenset(capabilities),
            platform=candidate.platform,
        )
        context = NodeContext(
            descriptor=descriptor,
            provider=None,
            process_manager=None,
            file_manager=None,
            scheduler=None,
            coordinator=None,
        )
        self._discovered.pop(node_id, None)
        self._contexts[node_id] = context
        return descriptor

    def revoke_trusted(self, node_id: NodeId) -> None:
        """Remove one trusted/authorised node from the registry.

        The local node can never be revoked; discovered candidates and
        placeholders that were never trusted are rejected. When the revoked
        node was selected, selection returns to the local node.
        """

        context = self.context(node_id)
        if context.descriptor.is_local:
            raise ValueError("The local node cannot be revoked")
        if context.descriptor.trust not in (
            NodeTrustState.TRUSTED,
            NodeTrustState.AUTHORISED,
        ):
            raise ValueError(f"Node is not trusted: {node_id}")
        del self._contexts[node_id]
        if self._selected_id == node_id:
            self._selected_id = self._local_id

    def set_display_name(self, node_id: NodeId, display_name: str) -> NodeDescriptor:
        """Rename one registered node, returning its updated descriptor."""

        context = self.context(node_id)
        context.descriptor = replace(context.descriptor, display_name=display_name)
        return context.descriptor

    def set_color(self, node_id: NodeId, color: str | None) -> NodeDescriptor:
        """Set one registered node's display colour, returning its descriptor."""

        context = self.context(node_id)
        context.descriptor = replace(context.descriptor, color=color)
        return context.descriptor
