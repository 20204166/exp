# Diagnostics Live Health Pulse Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refine the existing diagnostics page into a clearer live health pulse while preserving snapshot data, callbacks, refresh behavior, and public/test seams.

**Architecture:** Keep `maintenance/diagnostics.py` as the read-only snapshot and serialization owner. Keep `maintenance/ui/diagnostics_page.py` as the presentation owner, reusing or minimally extending existing `maintenance/ui/layout.py` and `maintenance/ui/styles.py`; do not add a runtime component or support package.

**Tech Stack:** Python 3.12, Tkinter/ttk, unittest, Ruff, Pyright, Mypy, existing `WidgetRecorder` and `tests/dump_ui.py` harness.

---

## File Map

- Modify `maintenance/ui/diagnostics_page.py`: render the live pulse, state-aware rows, responsive content, and copy feedback without changing callbacks or snapshot fields.
- Modify `maintenance/ui/layout.py` only if an existing primitive can own a genuinely reusable status/pulse layout mechanism.
- Modify `maintenance/ui/styles.py`: register named diagnostics state styles/tokens using existing semantic colors and fonts.
- Modify `tests/test_diagnostics_page.py`: behavior-first coverage for pulse values, state presentation, row reuse, empty states, and existing actions.
- Modify `tests/test_live_tk_resize.py` only if the existing diagnostics resize surface needs a contract assertion.
- Update `.ui/surface-map.json`, `.ui/design-language.md`, `.ui/reports/ui-audit.md`, `.ui/reports/ui-opposition-report.md`, and `.ui/reports/ui-validation-report.md` with rendered evidence; do not add runtime files.

## Task 1: Establish failing presentation contracts

**Files:** `tests/test_diagnostics_page.py`

- [ ] Add tests that construct the page through `WidgetRecorder` and assert the pulse exposes the existing snapshot-derived values: active work, recent failure, node count, and render pressure.
- [ ] Add tests for semantic state presentation: active work uses the busy/warning treatment, failures use danger treatment, and empty sections retain explicit empty text.
- [ ] Add a refresh test that renders a changed snapshot and verifies pulse/section widgets are reused rather than rebuilt.
- [ ] Add a copy-action test preserving the existing serialized payload and callback path.
- [ ] Run ` .venv/bin/python -m unittest tests.test_diagnostics_page -v`; expected result is failure for the new pulse/state assertions because the current page does not expose them.

## Task 2: Register canonical diagnostics presentation tokens

**Files:** `maintenance/ui/styles.py`, `maintenance/ui/layout.py`

- [ ] Search existing styles and primitives before adding anything; reuse `STYLE_HEALTHY`, `STYLE_HEALTH_WARNING`, `STYLE_DESCRIPTION`, `section_card`, `metric_row`, `page_status`, and shared spacing where their contracts match.
- [ ] If needed, add only named diagnostics styles that map to existing `success`, `warning`, `danger`, `text`, `secondary`, and `muted_text` tokens. Register them inside `configure_app_styles`; do not add literal colors in the page.
- [ ] If needed, add one presentation-only primitive for the pulse layout, parameterized by existing widget factories and tokens. Do not add diagnostic-specific meaning to `layout.py`.
- [ ] Run the focused page tests and style tests; expected result is that token/primitives tests pass while pulse behavior remains pending.

## Task 3: Implement the live health pulse and adaptive rows

**Files:** `maintenance/ui/diagnostics_page.py`

- [ ] Add the pulse using values already present in `DiagnosticsSnapshot`; do not alter `maintenance.diagnostics` models or serialization.
- [ ] Keep the current sections and exact values, but render state-aware labels/styles for active, failure, unavailable, empty, and normal states.
- [ ] Replace fixed diagnostic row wrapping with the existing resize-aware layout mechanism or a minimal extension of it, preserving headless widget factories.
- [ ] Preserve `DiagnosticsPageCallbacks`, `diagnostics:copy`, `focus_back`, one-second controller refresh, and all detailed docstrings in `maintenance/diagnostics.py`.
- [ ] Run ` .venv/bin/python -m unittest tests.test_diagnostics_page tests.test_diagnostics -v`; expected result is PASS.

## Task 4: Rendered evidence and interaction validation

**Files:** `.ui/*` evidence/report files and affected tests

- [ ] Run ` .venv/bin/python tests/dump_ui.py` using the existing harness and inspect desktop and narrow diagnostics output.
- [ ] Run ` .venv/bin/python -m unittest tests.test_live_tk_resize -v`; record a clean pass or the repository’s display-unavailable skip.
- [ ] Verify Back and Copy keyboard/focus paths, disabled/read-only state readability, live refresh stability, and no clipping at narrow width.
- [ ] Record opposition findings honestly in `.ui/reports/ui-opposition-report.md`; do not claim rendered quality without inspecting captured evidence.

## Task 5: Complete validation and diff review

- [ ] Run ` .venv/bin/python -m unittest discover -s tests -v`.
- [ ] Run ` .venv/bin/ruff check .` and ` .venv/bin/ruff format --check .`.
- [ ] Run ` .venv/bin/pyright` and ` .venv/bin/mypy --ignore-missing-imports`.
- [ ] Run ` git diff --check` and review the final diff for API, callback ordering, security, lifecycle, formatting, and unrelated architecture changes.
- [ ] Run a final repository search for duplicate pulse/status implementations and obsolete references; classify remaining matches as canonical, specialized, or test doubles.
