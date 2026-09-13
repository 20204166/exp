# Opt-In Full-System Storage Scan Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users explicitly opt into a broader local storage review while preserving the current Downloads scan and conservative cleanup behavior by default.

**Architecture:** Keep `Downloads` as the default scan root. When opted in, scan the local filesystem anchor (`/` on Unix, the system drive on Windows), while excluding protected/runtime trees and keeping files outside the user-owned cleanup roots review-only. Extend the existing scanner/analyzer/provider contracts with an explicit local scan-root value, and keep `FileManager` as the authoritative cleanup safety boundary. Persist the opt-in preference as an optional field compatible with existing schema-version-1 documents; remote providers remain on their existing contract unless separately designed.

**Tech Stack:** Python 3.12, Tkinter/ttk, `pathlib`, `unittest`, existing `AppPreferences`/`PreferencesStore`, `SystemScanner`, `DownloadScanner`, `FileManager`, `StorageDialog`, Ruff, Pyright, and Mypy.

---

## File Map

- Modify `maintenance/preferences.py`: own the persisted opt-in setting and default it to disabled.
- Modify `maintenance/ui/preferences_page.py` and `maintenance/ui/window_page_data.py`: present the setting and pass its value without owning storage semantics.
- Modify `maintenance/ui/window_preferences.py` and `window.py`: persist the setting and keep controller sequencing unchanged.
- Modify `maintenance/scanner.py`, `algo.py`, `maintenance/nodes.py`, and `maintenance/components/downloads.py`: carry an explicit local scan root while preserving legacy callers.
- Modify `maintenance/dialogs.py`: select the local scope, update copy/progress, and keep cleanup actions scoped.
- Modify `maintenance/actions.py`: accept only an explicit safe-root policy if cleanup scope is expanded; never make filesystem root an implicit allowed root.
- Modify `tests/test_preferences.py`, `tests/test_components.py`, `tests/test_storage_dialog.py`, `tests/test_storage_conservative.py`, and related contract tests.

## Task 1: Establish contracts

- [ ] Add failing tests for the disabled default, optional persisted field, and legacy preference documents.
- [ ] Add failing tests proving an explicit Downloads root produces current results and an explicit broader root is passed only to local scanning.
- [ ] Add failing tests proving cancellation, permission failures, symlink rejection, and cleanup-root validation remain fail-closed.
- [ ] Run `scripts/run_tests.sh tests.test_preferences tests.test_components tests.test_storage_conservative tests.test_storage_dialog -v`; expected result is failure only for the new contracts.

## Task 2: Persist the opt-in setting

- [ ] Add a boolean preference defaulting to `False`; load a missing field as `False`, reject malformed values by the existing defaults policy, and serialize it deterministically without changing existing public names.
- [ ] Add the setting to the Preferences page with copy that states scope, cost, and cleanup limits. Keep the control keyboard reachable and do not enable it implicitly from opening Storage Cleanup.
- [ ] Preserve save-failure rollback, status/error messaging, and `AppPreferences` immutability.

## Task 3: Thread an explicit scan root

- [ ] Extend the local scanner path as `scan_root: Path | None = None`, resolving `None` to the existing Downloads path; do not use a mode flag or silently change the default.
- [ ] Preserve progress callbacks, cancellation checks, hash-cache invalidation, ordering, duplicate detection, and legacy one-argument provider fallbacks.
- [ ] Keep remote `storage_candidates` requests unchanged until a remote scope/authorization contract exists; local preference state must never be serialized into a remote request accidentally.
- [ ] Run the focused scanner and remote contract tests before changing dialog behavior.

## Task 4: Define review and cleanup scope

- [ ] Make Storage Cleanup display the active scope, with copy such as `Reviewing Downloads` or `Reviewing the selected full-system scope` and a visible warning before a broad scan starts.
- [ ] Keep the broad scan cancellable, progress-reporting, and safe on permission errors, inaccessible mounts, disappearing files, symlinks, cycles, and very large result sets.
- [ ] Do not set `/` as an unrestricted `FileManager.allowed_root`. Define and test an explicit safe-root/owned-path policy; files outside that policy remain review-only and are rejected by the authoritative action layer.
- [ ] Require the existing confirmation flow for moving selected files, show the exact count and scope, and preserve read-only remote behavior.

## Task 5: Validate and document the flow

- [ ] Test first use (disabled), enabled local scan, save failure, restart persistence, cancel, partial permission failures, empty results, too many results, and cleanup rejection outside the allowed root.
- [ ] Test the unchanged default path against the existing Downloads fixtures and test that the scan scope is not sent through the remote protocol.
- [ ] Update help/settings copy and relevant architecture documentation; do not claim full-system cleanup is safe without tests for the root policy.
- [ ] Run `scripts/run_tests.sh tests.test_preferences tests.test_components tests.test_storage_conservative tests.test_storage_dialog tests.test_remote_contract tests.test_window -v`.
- [ ] Run `scripts/run_tests.sh`, `ruff check .`, `ruff format --check .`, `pyright`, `mypy --ignore-missing-imports`, and `git diff --check`.
- [ ] Run a performance baseline with representative file counts before enabling broad scans by default; success means opt-in behavior is preserved, not that full-system scans match Downloads latency.

## Fixed Safety Decisions

- [ ] Define “full system” as the local filesystem anchor, not a user-home approximation; the default remains Downloads and the broad mode is never implicit.
- [ ] Permit cleanup only for files under explicitly approved user-owned roots after the existing path, symlink, file-type, and race revalidation; candidates outside those roots are review-only and must be rejected by `FileManager`.
- [ ] Treat mounted volumes and system/runtime trees as scan inputs only when they pass the same traversal exclusions and permission checks; do not silently broaden cleanup authority to them.
