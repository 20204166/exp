"""Stable public interface for the System Analyzer component subsystem.

The component subsystem lives in responsibility modules beside this file:
`scan_support` (shared scan primitives), `process_safety`, `downloads`,
`gpu`, `background`, `catalog`, and `coordinator`. This package ``__init__``
re-exports the historical `maintenance.components` surface unchanged, so
existing imports and test monkeypatch seams keep resolving to the identical
objects. Generic external-command execution deliberately stays outside this
package in `maintenance.external_commands`.
"""

from .background import BackgroundTaskRunner
from .catalog import ResourceFeature, ResourceFeatureCatalog
from .coordinator import ScanCoordinator
from .downloads import (
    DownloadScanner,
    DownloadsPathResolver,
    HashFingerprint,
)
from .gpu import GPU_INFORMATION_UNAVAILABLE, GpuDetector, gpu_unavailable_message
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

__all__ = [
    "DOWNLOADS_SCAN_CANCELLED",
    "GPU_INFORMATION_UNAVAILABLE",
    "PROTECTED_PROCESS_NAMES",
    "BackgroundTaskRunner",
    "DownloadScanner",
    "DownloadsPathResolver",
    "GpuDetector",
    "HashFingerprint",
    "ProcessSafetyPolicy",
    "ProgressCallback",
    "ProgressTask",
    "ResourceFeature",
    "ResourceFeatureCatalog",
    "ScanCancelled",
    "ScanCoordinator",
    "check_cancelled",
    "gpu_unavailable_message",
    "normalize_username",
    "protected_process_pids",
    "require_psutil",
    "usernames_match",
    "windows_windll",
]
