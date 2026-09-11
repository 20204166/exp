"""Stable public interface for the System Analyzer component subsystem.

The component subsystem lives in responsibility modules beside this file:
`scan_support` (shared scan primitives), `process_safety`, `downloads`,
`gpu`, `temperature`, `background`, `catalog`, and `coordinator`. This package ``__init__``
re-exports the historical `maintenance.components` surface unchanged, so
existing imports and test monkeypatch seams keep resolving to the identical
objects. Generic external-command execution deliberately stays outside this
package in `maintenance.external_commands`.
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .background import BackgroundTaskRunner

from .catalog import ResourceFeature, ResourceFeatureCatalog
from .cluster_roles import (
    ClusterRole,
    CoordinatorEpoch,
    CoordinatorLease,
    FencingError,
    PromotionDecision,
    RoleAssignment,
    RoleAuthorizationError,
    RoleChange,
    RoleState,
    rejoin_as_worker,
)
from .cluster_storage import (
    CoordinatorTimeline,
    ResourceSnapshot,
    SnapshotBatch,
    StandbyBuffer,
    StorageStatus,
)
from .coordinator import ScanCoordinator
from .dashboard_scan import DashboardScanLifecycle
from .discovery_session import DiscoverySession, DiscoveryStartResult
from .downloads import (
    DownloadScanner,
    DownloadsPathResolver,
    HashFingerprint,
)
from .gpu import GPU_INFORMATION_UNAVAILABLE, GpuDetector, gpu_unavailable_message
from .network_discovery import (
    DEFAULT_TTL_SECONDS,
    SERVICE_TYPE,
    DiscoveryAdvertisement,
    DiscoveryEndpoint,
    NetworkDiscovery,
)
from .node_selection import NodeSelection
from .peer_connection import PeerConnectionManager
from .placement import (
    JobClass,
    PlacementDecision,
    PlacementPolicy,
    PlacementRequest,
    PlacementView,
    placement_view_for_context,
)
from .process_safety import (
    PROTECTED_PROCESS_NAMES,
    ProcessSafetyPolicy,
    normalize_username,
    protected_process_pids,
    usernames_match,
)
from .scan_support import (
    DOWNLOADS_SCAN_CANCELLED,
    ProgressCallback,
    ProgressTask,
    ScanCancelled,
    check_cancelled,
    require_psutil,
    windows_windll,
)
from .temperature import (
    TemperatureEvent,
    TemperaturePolicy,
    TemperatureSample,
    TemperatureScan,
    TemperatureSeriesSnapshot,
    TemperatureState,
    TemperatureTelemetry,
)


def __getattr__(name: str) -> Any:
    if name == "BackgroundTaskRunner":
        from .background import BackgroundTaskRunner

        return BackgroundTaskRunner
    raise AttributeError(name)


__all__ = [
    "DEFAULT_TTL_SECONDS",
    "DOWNLOADS_SCAN_CANCELLED",
    "GPU_INFORMATION_UNAVAILABLE",
    "PROTECTED_PROCESS_NAMES",
    "SERVICE_TYPE",
    "BackgroundTaskRunner",
    "ClusterRole",
    "CoordinatorEpoch",
    "CoordinatorLease",
    "CoordinatorTimeline",
    "DashboardScanLifecycle",
    "DiscoveryAdvertisement",
    "DiscoveryEndpoint",
    "DiscoverySession",
    "DiscoveryStartResult",
    "DownloadScanner",
    "DownloadsPathResolver",
    "FencingError",
    "GpuDetector",
    "HashFingerprint",
    "JobClass",
    "NetworkDiscovery",
    "NodeSelection",
    "PeerConnectionManager",
    "PlacementDecision",
    "PlacementPolicy",
    "PlacementRequest",
    "PlacementView",
    "ProcessSafetyPolicy",
    "ProgressCallback",
    "ProgressTask",
    "PromotionDecision",
    "ResourceFeature",
    "ResourceFeatureCatalog",
    "ResourceSnapshot",
    "RoleAssignment",
    "RoleAuthorizationError",
    "RoleChange",
    "RoleState",
    "ScanCancelled",
    "ScanCoordinator",
    "SnapshotBatch",
    "StandbyBuffer",
    "StorageStatus",
    "TemperatureEvent",
    "TemperaturePolicy",
    "TemperatureSample",
    "TemperatureScan",
    "TemperatureSeriesSnapshot",
    "TemperatureState",
    "TemperatureTelemetry",
    "check_cancelled",
    "gpu_unavailable_message",
    "normalize_username",
    "placement_view_for_context",
    "protected_process_pids",
    "rejoin_as_worker",
    "require_psutil",
    "usernames_match",
    "windows_windll",
]
