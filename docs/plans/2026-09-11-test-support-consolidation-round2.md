# Test Support Consolidation (Round 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the remaining semantic duplication in `tests/` that survived the round-1 consolidation: duplicate discovery fakes (`FakeBackend`, `FakeDiscovery`), a pervasive scanner-construction literal, repeated page-scaffolding wiring, and inline `FileCandidate` constructions.

**Architecture:** Extend the existing canonical test-support owners (`tests/support/scanner.py`, `tests/support/widget_recording.py`, `tests/support/models.py`) and add one new owner (`tests/support/discovery.py`) for the discovery fakes. Every migration preserves the exact observable contract of the old fake; no production code is touched.

**Tech Stack:** Python 3.10+, `unittest`, `unittest.mock`. Support modules never match `test*.py` so they are not discovered as tests.

---

## File Structure Map

- Create `tests/support/discovery.py` — shared `FakeBackend` + `FakeDiscovery` (canonical owners for the discovery-component surface).
- Modify `tests/support/scanner.py` — add `make_scanner()` factory.
- Modify `tests/support/widget_recording.py` — add `WidgetRecorder.page_kwargs()` + `WidgetRecorder.button_with_text()`.
- Modify `tests/support/models.py` — add `make_file_candidate()` builder.
- Migrate callers: `test_network_discovery.py`, `test_discovery_end_to_end.py`, `test_coordinator_discovery.py`, `test_discovery_session.py`, plus the ~12 files using the `SystemScanner(Path("Downloads"))` literal, the 5 page-test files, and the 3 `FileCandidate` sites.
- Regression net: existing focused tests per file + the full suite.

## Task Overview

- **Task 1:** Extract `FakeBackend` to `tests/support/discovery.py`; migrate 2 files.
- **Task 2:** Extract unified `FakeDiscovery` to `tests/support/discovery.py`; migrate 2 files.
- **Task 3:** Add `make_scanner()` and migrate the `SystemScanner(Path("Downloads"))` literal (~12 files).
- **Task 4:** Add `page_kwargs()`/`button_with_text()`; migrate 5 page-test files.
- **Task 5:** Add `make_file_candidate()`; migrate 3 files.
- **Task 6:** Full validation and commit.

---

### Task 1: Extract `FakeBackend` to support/discovery.py

**Files:**
- Create: `tests/support/discovery.py`
- Modify: `tests/test_network_discovery.py:61-95`
- Modify: `tests/test_discovery_end_to_end.py:25-50`

- [ ] **Step 1: Create the canonical discovery fake module**

Create `tests/support/discovery.py`:

```python
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
```

This is the superset of the two local fakes (the `test_network_discovery` version); the `test_discovery_end_to_end` version is a strict subset, so the superset satisfies both consumers.

- [ ] **Step 2: Migrate `test_network_discovery.py`**

- Delete the local `FakeBackend` class (lines 61-90).
- Keep `FailingStartBackend(FakeBackend)` but make it subclass the imported one:

```python
from tests.support.discovery import FakeBackend


class FailingStartBackend(FakeBackend):
    def start(self, advertisement: DiscoveryAdvertisement) -> None:
        super().start(advertisement)
        raise RuntimeError("bind failed")
```

- [ ] **Step 3: Migrate `test_discovery_end_to_end.py`**

- Delete the local `FakeBackend` class (lines 26-50).
- Add `from tests.support.discovery import FakeBackend`.

- [ ] **Step 4: Run the affected tests**

Run: `python3 -m unittest tests.test_network_discovery tests.test_discovery_end_to_end -v`
Expected: all `ok`.

- [ ] **Step 5: Commit**

```bash
git add tests/support/discovery.py tests/test_network_discovery.py tests/test_discovery_end_to_end.py
git commit -m "test: share the in-memory discovery backend fake"
```

---

### Task 2: Extract unified `FakeDiscovery` to support/discovery.py

**Files:**
- Modify: `tests/support/discovery.py`
- Modify: `tests/test_coordinator_discovery.py:15-57`
- Modify: `tests/test_discovery_session.py:12-26`

- [ ] **Step 1: Add `FakeDiscovery` to support/discovery.py**

Append to `tests/support/discovery.py`:

```python
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
```

This preserves both contracts: the session fake's `events` log and the coordinator fake's flags/`emit`/`expire_stale` surface plus its `RetryDiscovery` behavior via `fail_next_start`.

- [ ] **Step 2: Migrate `test_coordinator_discovery.py`**

- Delete the local `FakeDiscovery` and `RetryDiscovery` classes (lines 15-57).
- Add `from tests.support.discovery import FakeDiscovery`.
- Replace the single `RetryDiscovery()` call (line 135) with `FakeDiscovery(fail_next_start=True)`.
- All `FakeDiscovery()` and `FakeDiscovery(available=False)` calls work unchanged.

- [ ] **Step 3: Migrate `test_discovery_session.py`**

- Delete the local `FakeDiscovery` class (lines 12-26).
- Add `from tests.support.discovery import FakeDiscovery`.
- `FakeDiscovery(self.events)` at line 43 works unchanged (events positional).

- [ ] **Step 4: Run the affected tests**

Run: `python3 -m unittest tests.test_coordinator_discovery tests.test_discovery_session -v`
Expected: all `ok`.

- [ ] **Step 5: Commit**

```bash
git add tests/support/discovery.py tests/test_coordinator_discovery.py tests/test_discovery_session.py
git commit -m "test: share the configurable discovery component fake"
```

---

### Task 3: Add `make_scanner()` and migrate the scanner literal

**Files:**
- Modify: `tests/support/scanner.py`
- Modify: `tests/test_cpu_sampling.py`, `tests/test_components.py`, `tests/test_gpu_concurrency.py`, `tests/test_maintenance.py`, `tests/test_thermal_card.py`, `tests/test_process_table.py`, `tests/test_trash_size_cache.py`, `tests/test_scanner_static_cache.py`, `tests/test_network_card.py`, `tests/test_logging_setup.py`, `tests/test_gpu_name.py`

- [ ] **Step 1: Add the factory to support/scanner.py**

Add to `tests/support/scanner.py` (needs `from pathlib import Path` in its imports):

```python
def make_scanner(path: Path = Path("Downloads")) -> SystemScanner:
    """Build a scanner rooted at the canonical test Downloads directory."""

    return SystemScanner(path)
```

- [ ] **Step 2: Migrate the literal in each test file**

For every `SystemScanner(Path("Downloads"))` occurrence in the files above, replace it with `make_scanner()` and add `make_scanner` to that file's `from tests.support.scanner import ...` line. Where a file already imports from `tests.support.scanner` (e.g. `test_maintenance.py`), just add the name. The two `_new_scanner` helpers in `test_gpu_concurrency.py` and `test_cpu_sampling.py` keep their specialized bodies but construct via `make_scanner()`:

```python
def _new_scanner(self) -> SystemScanner:
    scanner = make_scanner()
    scanner.GPU_QUERY_TIMEOUT_SECONDS = 0.05
    scanner.GPU_QUERY_ABANDON_SECONDS = 0.05
    self._scanner = scanner
    return scanner
```

- [ ] **Step 3: Verify no literal remains**

Run: `grep -rn "SystemScanner(Path(\"Downloads\"))" tests/test_*.py`
Expected: no output.

- [ ] **Step 4: Run the affected tests**

Run: `python3 -m unittest tests.test_cpu_sampling tests.test_components tests.test_gpu_concurrency tests.test_maintenance tests.test_thermal_card tests.test_process_table tests.test_trash_size_cache tests.test_scanner_static_cache tests.test_network_card tests.test_logging_setup tests.test_gpu_name -q`
Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add tests/support/scanner.py tests/test_*.py
git commit -m "test: centralize the canonical test scanner factory"
```

---

### Task 4: Add `page_kwargs()`/`button_with_text()` and migrate page scaffolding

**Files:**
- Modify: `tests/support/widget_recording.py`
- Modify: `tests/test_cluster_page.py`, `tests/test_settings_home.py`, `tests/test_nodes_connections_page.py`, `tests/test_preferences_page.py`, `tests/test_diagnostics_page.py`

- [ ] **Step 1: Add the helpers to `WidgetRecorder`**

In `tests/support/widget_recording.py`, add two methods to `WidgetRecorder` (after `label_with_text`):

```python
def page_kwargs(self) -> dict[str, Any]:
    """Return the shared recorder widget classes used by headless page tests."""

    return {
        "frame_cls": self.frame_cls(),
        "label_cls": self.label_cls(),
        "style_frame_cls": self.style_frame_cls(),
        "style_label_cls": self.style_label_cls(),
        "button_cls": self.button_cls(),
        "canvas_cls": self.canvas_cls(),
        "scrollbar_cls": self.scrollbar_cls(),
    }

def button_with_text(self, text: str) -> RecordingWidget:
    """Return the first recorded button whose ``text`` equals ``text``."""

    return next(
        widget
        for widget in self.widgets("button")
        if widget.kwargs.get("text") == text
    )
```

- [ ] **Step 2: Migrate `make_page`/`make_home` scaffolding**

In `test_cluster_page.py`, `test_settings_home.py`, `test_nodes_connections_page.py`, `test_preferences_page.py`, and `test_diagnostics_page.py`, replace the repeated 7-line `frame_cls=recorder.frame_cls(), label_cls=..., style_frame_cls=..., style_label_cls=..., button_cls=..., canvas_cls=..., scrollbar_cls=...` wiring with `**recorder.page_kwargs(),`. Page-specific extras (e.g. `checkbutton_cls`, `combobox_cls`, `entry_cls`, `spinbox_cls`, `progressbar_cls`, `var_factory`, `boolean_var_factory`) remain explicit.

- [ ] **Step 3: Migrate the button finders**

- In `test_cluster_page.py`, replace `open_button(recorder)` bodies with `recorder.button_with_text("Open")` (or migrate call sites to the method and delete the helper).
- In `test_nodes_connections_page.py`, replace `button_with_text(recorder, text)` bodies with `recorder.button_with_text(text)` (migrate call sites and delete the helper).
- Leave `cpu_spinbox` in `test_preferences_page.py` as-is (it filters by `textvariable`, not `text`).

- [ ] **Step 4: Run the affected tests**

Run: `python3 -m unittest tests.test_cluster_page tests.test_settings_home tests.test_nodes_connections_page tests.test_preferences_page tests.test_diagnostics_page -v`
Expected: all `ok`.

- [ ] **Step 5: Commit**

```bash
git add tests/support/widget_recording.py tests/test_cluster_page.py tests/test_settings_home.py tests/test_nodes_connections_page.py tests/test_preferences_page.py tests/test_diagnostics_page.py
git commit -m "test: share page scaffolding and button lookup helpers"
```

---

### Task 5: Add `make_file_candidate()` and migrate inline constructions

**Files:**
- Modify: `tests/support/models.py`
- Modify: `tests/test_storage_dialog.py`, `tests/test_cluster.py`, `tests/test_remote_contract.py`

- [ ] **Step 1: Add the builder to support/models.py**

Add to `tests/support/models.py` (needs `from pathlib import Path` and `from datetime import datetime, timezone` — `datetime`/`timezone` are already imported):

```python
def make_file_candidate(
    path: Path,
    *,
    size: int = 10,
    modified_at: datetime | None = None,
    reason: str = "Large file",
) -> FileCandidate:
    """Build a file candidate with a deterministic modification time."""

    return FileCandidate(
        path,
        size,
        modified_at or datetime(2024, 1, 1, tzinfo=timezone.utc),
        reason,
    )
```

Add `FileCandidate` to the existing `from maintenance.models import ...` line.

- [ ] **Step 2: Migrate inline constructions**

- In `tests/test_storage_dialog.py`, replace the 7 inline `FileCandidate(path, size, datetime(2024, 1, 1, tzinfo=timezone.utc), reason)` constructions with `make_file_candidate(path, size=..., reason=...)`.
- In `tests/test_cluster.py:296` and `tests/test_remote_contract.py:167`, replace `FileCandidate(Path("/tmp/x"), 10, NOW/_now(), "reason")` with `make_file_candidate(Path("/tmp/x"), reason="reason")` (keeping each file's own timestamp where it asserts freshness).

- [ ] **Step 3: Run the affected tests**

Run: `python3 -m unittest tests.test_storage_dialog tests.test_cluster tests.test_remote_contract -q`
Expected: `OK`.

- [ ] **Step 4: Commit**

```bash
git add tests/support/models.py tests/test_storage_dialog.py tests/test_cluster.py tests/test_remote_contract.py
git commit -m "test: centralize the file candidate builder"
```

---

### Task 6: Final validation and commit

**Files:** none (validation only)

- [ ] **Step 1: Run the full test suite**

Run: `python3 -m unittest discover -s tests -q`
Expected: `Ran 1253 tests ... OK` (unchanged count; migrations preserve behavior).

- [ ] **Step 2: Run static sanity checks**

Run: `python3 -m compileall -q maintenance tests && git diff --check`
Expected: exit 0, no output.

- [ ] **Step 3: Check for unused imports in touched files**

Run a quick AST-based unused-import scan over the modified files (imports added for `make_scanner`/`FakeBackend`/`FakeDiscovery`/`make_file_candidate` must all be referenced; removed local classes must not leave dangling imports like `Any`, `Event`, or `DiscoveryAdvertisement`).
Expected: no unused imports.

- [ ] **Step 4: Commit any leftover changes**

```bash
git add -A
git commit -m "test: finalize round-two test support consolidation"
```
Only run if Step 3 found stragglers; otherwise skip.

---

## Self-Review Notes

- **Spec coverage:** Every remaining duplication candidate from the round-1 audit maps to a task: `FakeBackend` (Task 1), `FakeDiscovery` (Task 2), `SystemScanner(Path("Downloads"))` literal (Task 3), page-scaffolding wiring + button finders (Task 4), inline `FileCandidate` (Task 5). Intentionally kept separate: `FakeStyle`, `FakePage`, `FakeProvider`, `FakeManager`, `FakeNodesPage`, `PolicyProcess`/`FakeProcess`/`ActionProcess` (distinct psutil contracts), `cpu_spinbox` finder (different predicate), and the ~90 inline paddings in `dialogs.py` (separate surface).
- **No placeholders:** All steps carry exact code, paths, commands and expected output.
- **Type consistency:** `FakeBackend(listener, *, available=True)`, `FakeDiscovery(events=None, *, available=True, fail_next_start=False)`, `make_scanner(path=Path("Downloads"))`, `make_file_candidate(path, *, size=10, modified_at=None, reason="Large file")` are defined once and referenced verbatim by the migrations.
- **Bounded scope:** No production code changes; support modules stay test-only; no new test discovery (support names don't match `test*.py`).