# Windows / macOS Cross-Platform Compatibility Audit + Fix-Forward — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Every task below also names which skill(s) already installed in `.claude/skills/` (mirrored from `.opencode/skills/`) must be invoked to complete it — do not substitute ad hoc process for a named skill's workflow.

**Goal:** Audit the real repository for genuine Windows/macOS compatibility defects and fix only what is proven broken, while keeping Linux's verified behavior as a hard regression baseline — with the Thermals page "Waiting for samples" defect on non-Linux platforms as the mandatory, root-caused, fixed-first priority.

**Architecture:** Platform-specific acquisition (`maintenance/scanner_support/*`) stays specialized per OS; a shared normalized contract (`maintenance/models.py::ResourceSummary`/`CapabilityState`, `maintenance/components/temperature.py::TemperatureSample`/`TemperatureTelemetry`) carries results into platform-neutral application/UI code (`maintenance/ui/*`). This plan does not change that architecture — it audits whether every boundary actually honors the contract, and repairs the boundary where it doesn't.

**Tech Stack:** Python 3.10+, Tkinter/ttk, psutil, ctypes/IOKit (macOS SMC), PowerShell/WMI (Windows), `unittest` (not pytest — verified absent from this repo, see the Phase 0 correction note below), ruff, pyright, mypy.

**No implementation happens as part of writing this plan.** This document is the deliverable. Every code snippet below is illustrative of the intended fix and must still go through failing-test-first + adversarial review at execution time, per the named skills.

---

## Grounding: what is already verified about this repo (read directly, not assumed)

This app already has a materially good cross-platform skeleton — the audit's job is mostly to *verify* and *close gaps*, not build from scratch:

- `maintenance/models.py:13-31` — `CapabilityState` already has the exact vocabulary the spec asks for (`SUPPORTED`, `UNSUPPORTED`, `TEMPORARILY_UNAVAILABLE`, `NO_DATA`, `PERMISSION_LIMITED`, `NOT_VERIFIED_ON_NATIVE_PLATFORM`).
- `maintenance/scanner_support/gpu.py:236-335` — GPU already has separate `_mac_gpu_probe`/`_windows_gpu_probe`/`_linux_gpu_probe` (via `system_profiler`, PowerShell CIM, `lspci`/NVML) feeding one shared `GpuProbe` contract — the pattern the rest of the audit should hold acquisition code to.
- `maintenance/components/downloads.py:54-114` — `DownloadsPathResolver` already resolves Windows `USERPROFILE`/OneDrive-redirected Downloads and has a `Downloads.__unavailable__` sentinel fallback.
- `maintenance/scanner_support/storage.py:20-88` — Trash size already branches Windows (`SHQueryRecycleBinW` via ctypes), Darwin (`~/.Trash`), Linux (`~/.local/share/Trash/files`).
- `docs/CAPABILITY_TRANSPARENCY_2026-09-10.md` — an existing, honest provider matrix. It already states thermals on macOS/Windows are **"Not verified on native platform"** and that "Provider fakes cover Linux, macOS, and Windows dispatch" (mocked, not native). This is the authoritative prior admission that native validation never happened — Task 0.3 must re-verify this is still true before trusting it.
- `docs/performance/simulated-macos/` and `docs/performance/simulated-windows/` — prior performance numbers are explicitly labeled *simulated*, confirming no native macOS/Windows execution evidence exists yet anywhere in the repo.
- Git history already shows **at least 8 prior thermal-focused commits** (`4ff5b59` Apple SMC reads, `5618e7b` macOS SMC release, `1847a00` "gate sensors on platform", `46e23e4` "validate remote thermal samples", `f0dd2d8` "Windows thermal graph support", plus `4afb334`, `90af531`, `a1dd96c`, `ba07da3`) — the defect has survived multiple targeted attempts. Section 57's rule applies directly: **audit what those changes already did before adding another fallback on top.**

### Root-cause hypothesis for "Waiting for samples" (evidence-based, not fabricated — must still be proven per Task 2.4 before fixing)

Traced the full pipeline read-only:

1. `maintenance/scanner_support/dashboard.py:1264-1274` — `_temperature_sensors_supported(system)` returns `True` for `"Linux"`, `"Darwin"`, `"Windows"` **unconditionally** — it asserts the *platform* can attempt thermal reads, not that *this machine's hardware* has a sensor. It never returns `UNSUPPORTED`.
2. `dashboard.py:1200-1261` (`_temperature_scan_windows`) and `smc.py:234-267` (`read_smc_temperatures`) both **fail closed to an empty result** on any problem (no ACPI zone, Apple Silicon, IOKit missing, PowerShell failure) — this is correct fail-soft behavior, but it means "no sensor on this hardware" and "sensor read glitched this cycle" are indistinguishable by the time they reach the caller: both look like an empty `TemperatureScan`.
3. `dashboard.py:404-429` / `:591-620` (`_cpu_resource`, `_storage_resource`) hard-code `capability=CapabilityState.SUPPORTED` on the **card** (CPU/Storage/GPU/Battery readability), independent of whether `temperature_samples` was empty. This is correct for the card itself (CPU usage % is genuinely supported everywhere) but this is the *only* capability signal that ever reaches the UI for that key.
4. `maintenance/ui/window_components.py:269-286` (`observe_capability`) writes that same **card-level** capability into `controller._capabilities["cpu"]` (etc.) — there is no separate `"cpu_temperature"` (or similar) capability key anywhere in the codebase (confirmed by grep — `_capabilities` is only ever populated per top-level resource key).
5. `maintenance/ui/thermals_page.py:133-147` (`_should_show`) reads that same card-level capability to decide whether to keep showing a thermal card, and `maintenance/ui/thermal_graph.py:185-186` renders "Waiting for the first sample" whenever state is `NO_DATA` and the card is still shown.

**Net effect:** on any real Windows machine without an exposed ACPI thermal zone, or any Apple Silicon Mac (SMC temperature keys return errors by design — `smc.py:30`), the CPU/GPU/Storage capability is `SUPPORTED` (correctly — those cards work) forever, so the Thermals card is never hidden and never told "unsupported" — it just accumulates zero samples and displays "Waiting for the first sample" **permanently**, because nothing in the pipeline ever authoritatively declares *thermal* capability separate from *card* capability. This plausibly explains why every prior attempt (which touched acquisition, graph rendering, or "platform gating" at the `_temperature_sensors_supported` level) didn't fix it: none of them added a thermal-specific capability signal distinct from the card's own.

Phase 2 exists to **prove or disprove** this hypothesis with real evidence (native or fixture-driven) before Phase 3 touches any code — per BugGuard's "a risk is not a bug without proof" rule.

---

## Skills Legend — which `.claude/skills/` skill governs which task

Every skill copied into `.claude/skills/` is accounted for below, either assigned a role or explicitly marked not applicable. Do not invent workflow that a named skill already owns.

| Skill | Role in this plan |
|---|---|
| `brainstorming` | Already run this session to scope this plan against real repo state; not re-invoked during execution. |
| `writing-plans` | Produced this document. |
| `BugGuard` | **Primary workflow for the whole pass.** Mode B (standalone bug-hunt, no code changes) drives every Audit task below. Mode A (code-edit validation) drives every Fix task. Mode D (security assurance) is mandatory for the remote listener/TLS (Phase 8) and process-termination (Phase 5) surfaces. Mode C only if a fix is purely a performance change (rare here). |
| `systematic-debugging` | Governs Phase 2 (thermal pipeline trace) — root-cause tracing before any fix is proposed, per its own trigger ("before proposing fixes"). |
| `test-driven-development` | Governs the failing-test-first step inside every Fix task in Phases 3–9. |
| `consolidating-responsibilities` | Governs Phase 10 — search-before-create audit of any new platform helper, reuse over extraction. |
| `evolving-apis-and-schemas` | Governs any change to the `ResourceSummary`/`TemperatureRenderState` contract in Phase 3 (verified real propagation path: `maintenance/cluster.py`'s `resource_summary_from_dict`/`temperature_sample_from_dict`, not `remote_support/protocol.py` — see Phase 3 Step 5) and any remote wire-shape change in Phase 8. Verified this session: `maintenance/remote_support/protocol.py` genuinely is the right file for that role — its module docstring and content confirm it owns the signed request/response envelope (`sign_request`/`verify_request`, etc.), the replay cache, freshness window, and the operation/role/capability metadata tables shared by both `RemoteService` (server) and `AuthenticatedNodeProvider` (client); any Phase 8 change to what capabilities/operations a node can advertise or request must preserve this envelope's versioning (`REMOTE_PROTOCOL_VERSION`). |
| `investigating-performance` | Governs Phase 11 — proving no new polling thread/timer/subprocess-per-render was introduced. |
| `dispatching-parallel-agents` | Governs Phase 1 and Phase 4 — the per-subsystem audits (CPU/Memory/Storage/GPU/Network/Battery/Downloads) are independent with no shared state and should be dispatched in parallel rather than serially. |
| `designing-user-experience` | Governs the empty/error/no-sensor state wording work in Phase 3 and Phase 4 (truthful capability copy, not just "Waiting..."). |
| `UI` | Governs Phase 7 — Tk/ttk rendering, resize, DPI, dialog and Thermals-page visual-state audit (hands correctness findings back to BugGuard rather than fixing logic itself). |
| `building-accessible-interfaces` | Governs the keyboard-navigation/focus/contrast check inside Phase 7 for Tk dialogs and the Thermals page back-button/scroll behavior. |
| `reviewing-interface-quality` | Governs the closing quality gate at the end of Phase 7, before Phase 7 is marked done. |
| `verifying-before-completion` | Governs Phase 13 (native smoke tests) and Phase 14 (final validation) — no "tests pass"/"fixed" claim is made without running the commands and pasting real output. |
| `repo-context-curator` | Governs Phase 14's step of folding the verified platform matrix and thermal root-cause lesson back into `AGENTS.md`/`docs/CAPABILITY_TRANSPARENCY_2026-09-10.md` so it isn't re-litigated next time. |

**Explicitly not used, with reason** (so nothing is silently skipped):

- `audit-lr-drift` — this repo has no `./lr` CLI or `surface_drift_check.py` (confirmed absent); the skill's own scope note says do not use it outside that tooling.
- `Compliance` — this is a technical compatibility audit, not UK legal/regulatory research; out of scope by the skill's own description.
- `creating-skills` — no new skill is being authored or modified by this work.
- `applying-themes`, `designing-frontend-interfaces` — both are web/visual-design-system skills (color/type systems, HTML/CSS aesthetic direction); this is a Tkinter desktop app with an existing `maintenance/ui/styles.py` token set, not a themable web surface. `UI` and `designing-user-experience` cover the actual Tk-relevant ground.

---

## File Structure (audit artifacts this plan creates)

- `docs/platform_audit/PLATFORM-MATRIX.md` — the living capability matrix (Section 58-style table), updated as each phase completes.
- `docs/platform_audit/THERMAL-ROOT-CAUSE.md` — the Phase 2 pipeline trace table and proof/disproof of the hypothesis above.
- `docs/bug_hunts/bugs_found_N.md` / `docs/bug_hunts/index.md` — existing BugGuard ledger (already present under `docs/bug_hunts/`); every audit finding in Phases 1, 4–9 is logged here, not in a new file.
- `docs/security_reviews/SEC-YYYYMMDD-NNN-review.md` — BugGuard Mode D artifacts for Phase 5 and Phase 8.
- No application code files are named for creation here (Phase 3's illustrative fix touches existing files only — see Phase 3).

---

## Phase 0 — Baseline

**Skill:** `BugGuard` (Mode B setup — this is the A1/"before editing" discovery step, run once for the whole pass).

- [x] **Step 1: Record commit and tree state** — captured in the baseline artifact; the only persistent untracked path is the pre-existing `.claude/` directory, which was not touched.

```bash
git rev-parse HEAD
git status --short
git log --oneline -10
```

- [x] **Step 2: Run the existing full validation suite as-is on this (Linux) environment and capture the baseline** — the documented bare `python` command is unavailable on this host; the equivalent `.venv/bin/python` command was run and its results are recorded, including the baseline static-check limitations.

**Corrected this session — this repo does not use `pytest`.** The original draft used `python -m pytest tests/ -q` throughout the plan (Phases 0, 3, 12, 13). Verified three independent ways: (1) `AGENTS.md:11` explicitly states "Tests are `unittest` modules under the `tests` package ... via `python -m unittest discover -s tests -v` and via single-module invocation `python -m unittest tests.test_window -v`"; (2) `README.md:316,322,329,358` document the exact same `python -m unittest ...` invocations, never `pytest`; (3) `.venv/bin/python -m pytest --version` in this repo's own virtualenv fails with `No module named pytest` — it is not even installed, let alone declared in `pyproject.toml`/`requirements.txt`/`requirements-dev.txt` (checked all three this session — only `ruff`, `pyright`, `mypy` are pinned dev dependencies). Every `python -m pytest ...` command anywhere in this plan would fail outright at execution time. This phase's own commands are fixed below; **Phases 3, 12, and 13 still have the same defect and need the identical fix** — flagging here since Phase 0 establishes the baseline convention the rest of the plan must match.

The exact command set is independently confirmed twice over: `pyproject.toml:21` documents it verbatim in a comment ("the `ruff check .`, `ruff format --check .`, `pyright`, and `mypy --ignore-missing-imports` gates") and `pyrightconfig.json`'s `include` list (`maintenance`, `window.py`, `main.py`, `algo.py`, `tests`) confirms `pyright`'s scope matches what's below:

```bash
python -m unittest discover -s tests -q 2>&1 | tee /tmp/baseline-unittest.log
ruff check . 2>&1 | tee /tmp/baseline-ruff.log
ruff format --check . 2>&1 | tee /tmp/baseline-format.log
pyright 2>&1 | tee /tmp/baseline-pyright.log
mypy --ignore-missing-imports . 2>&1 | tee /tmp/baseline-mypy.log
```

Record pass/fail counts verbatim in `docs/platform_audit/PLATFORM-MATRIX.md` under a "Baseline" heading. Any pre-existing failure found here is out of scope for this pass (per the spec's "do not attribute existing unrelated failures to this pass") — list it but do not fix it unless it blocks a thermal-pipeline task.

- [x] **Step 3: Re-verify the existing compatibility claims are still accurate** — the capability and remote-thermal documents were read and deltas are recorded in the matrix.

Read `docs/CAPABILITY_TRANSPARENCY_2026-09-10.md` in full and `docs/plans/2026-09-10-remote-thermal-sample-validation.md` in full. Note any claim that current code no longer matches (e.g., if `_temperature_sensors_supported` or the SMC/Windows probes changed since that doc was written). Record deltas in `docs/platform_audit/PLATFORM-MATRIX.md`.

- [x] **Step 4: Commit the baseline artifact** — baseline evidence is committed in the audit documentation history.

```bash
git add docs/platform_audit/PLATFORM-MATRIX.md
git commit -m "docs: record cross-platform audit baseline"
```

---

## Phase 1 — Repository-wide platform-assumption inventory

**Skills:** `BugGuard` (Mode B, standalone audit — no code changes) driving the workflow; `dispatching-parallel-agents` to run the independent greps/subsystem scans concurrently rather than serially.

- [x] **Step 1: Dispatch parallel, independent searches** (per `dispatching-parallel-agents`) — the platform searches and corrected false-positive classifications were rerun against the current tree.

```bash
grep -rn "sys\.platform" maintenance/ main.py window.py
grep -rn "platform\.system()" maintenance/ main.py window.py
grep -rn "os\.name" maintenance/ main.py window.py
grep -rln "subprocess" maintenance/
grep -rn "wmic\|powershell\|system_profiler\|ioreg\|nvidia-smi\|lspci\|sensors_temperatures" maintenance/
grep -rn "/proc\|/sys/" maintenance/
grep -rn "send2trash" maintenance/
```

Real results captured this session (re-run at execution time — this is starting evidence, not a substitute for re-verifying):

- `sys\.platform`: **1 hit** — `maintenance/scanner_support/smc.py:148` (`if sys.platform != "darwin":`).
- `platform\.system()`: **7 hits across 6 files** — `maintenance/preferences.py:169`, `maintenance/components/downloads.py:63`, `maintenance/components/node_context.py:44`, `maintenance/scanner_support/dashboard.py:277,485,1097`, `maintenance/scanner_support/storage.py:25,81`.
- `os\.name`: **2 hits** — `maintenance/scanner_support/gpu.py:274`, `maintenance/scanner_support/dashboard.py:1217` (both `if os.name == "nt"`).
- `subprocess` (files, not line count): **9 files** — `maintenance/external_commands.py`, `maintenance/remote_security.py`, `maintenance/scanner.py`, `maintenance/ui/window_discovery.py`, `maintenance/components/gpu.py`, `maintenance/scanner_support/gpu.py`, `maintenance/scanner_support/dashboard.py`, plus `maintenance/README.md` and `maintenance/components/README.md` (docs mentions, not code — exclude from the code audit). `maintenance/external_commands.py` is very likely the canonical subprocess-runner this plan's Phase 6 should hold every other subprocess call site to (per Section 40's canonical-reuse rule) — confirm this at Phase 6 time, not assumed here.
- `wmic\|powershell\|system_profiler\|ioreg\|nvidia-smi\|lspci\|sensors_temperatures`: **2 files** — `maintenance/scanner_support/gpu.py`, `maintenance/scanner_support/dashboard.py`.
- `/proc\|/sys/`: **1 genuine hit, 3 false positives.** The real one is `maintenance/scanner_support/dashboard.py:489` (`scanner_module.Path("/proc/swaps").read_text()`, Linux swap accounting). The other three matches (`maintenance/remote.py:18`, `maintenance/README.md:52`'s prose, `maintenance/components/network_discovery.py:11`) are substring false-positives — the pattern `/proc` also matches inside the English word "**/proc**ess" (e.g. "CPU/RAM/process"), not an actual filesystem path. Use a tighter pattern at execution time, e.g. `grep -rn '"/proc\|"/sys/'` (quoted-path-literal form) to avoid re-triggering this.
- `send2trash`: **2 files** — `maintenance/actions.py` (real usage) and `maintenance/README.md` (doc mention).

- [x] **Step 2: Classify every hit** into the required platform categories — classifications and evidence are recorded in `docs/platform_audit/PLATFORM-MATRIX.md`.

- [x] **Step 3: For every `UNSAFE ASSUMPTION` found, open a BugGuard Mode B candidate** — no unsafe assumption survived classification, so no new candidate was opened in this phase.

Follow `BugGuard`'s `mode_b_main_auditor.md` threshold rules exactly: create the candidate in `docs/bug_hunts/bugs_found_N.md`, run the required opposition reviewers at the threshold the risk level demands (full B7 for anything touching auth/session/process/storage/TLS boundaries per BugGuard's own high-risk list), and do not fix anything in this phase — Mode B is audit-only.

- [x] **Step 4: Commit the inventory** — inventory evidence is included in the committed platform-audit documentation.

```bash
git add docs/platform_audit/PLATFORM-MATRIX.md docs/bug_hunts/
git commit -m "docs: repository-wide platform assumption inventory"
```

---

## Phase 2 — Thermal pipeline trace and root-cause proof (MANDATORY FIRST PRIORITY)

**Skill:** `systematic-debugging`, invoked directly (this is the canonical "before proposing fixes" root-cause tracing skill), with `BugGuard` Mode B owning the candidate/evidence ledger around it.

- [x] **Step 1: Declare BugGuard Mode B for the thermal candidate**

```text
BugGuard mode: Mode B - standalone bug-hunt
Candidate: BUG-<today>-001 "Thermals page stuck at Waiting for samples on non-Linux"
Threshold: full B7 (high-risk: user-facing state that has survived multiple prior fix attempts)
```

- [x] **Step 2: Build the boundary table** in `docs/platform_audit/THERMAL-ROOT-CAUSE.md` using `systematic-debugging`'s root-cause-tracing method, covering every boundary A–P from the spec (sensor availability → acquisition → raw shape → classification → validation → `TemperatureSample` → `ResourceSummary.temperatures` → `TemperatureTelemetry.record_summary` → history → `TemperatureRenderState` → `ThermalsPage.render` → `_should_show` → `TelemetryMiniGraph`/`thermal_graph.py` draw). Use the file:line citations already gathered in this plan's Grounding section as the starting evidence. The two boundaries this plan previously flagged as "not yet fully traced" are now CONFIRMED (verified this session, not left as a hedge):

  - **`maintenance/components/coordinator.py` does not intercept/transform the thermal render path.** Grepped the full 848-line file for `temperature`/`thermal`/`render`: exactly two hits, both irrelevant — a comment on GPU refresh cadence (`coordinator.py:49`, "GPU usage/temperature moderate (3s)") and an unrelated docstring note about cache replay (`coordinator.py:322`, "`last_result` / `store`, so a reopened surface renders immediately"). No thermal-specific logic exists in this file at all.
  - **`context.capabilities` and `controller._capabilities` are confirmed the same dict object, not a copy.** `maintenance/ui/window_node_runtime.py:226-238` (`sync_selected_context_mirrors`) does `controller._capabilities = context.capabilities` (line 232) — a reference assignment. `maintenance/ui/window_components.py:269-286` (`observe_capability`) then reads/mutates it via `controller.__dict__.setdefault("_capabilities", {})` (line 273) — since `window.py:223` declares `self._capabilities: dict[str, CapabilityState] = {}` as a plain instance attribute (no property indirection), `setdefault` returns the exact dict `sync_selected_context_mirrors` just pointed at `context.capabilities`, so `observe_capability`'s in-place mutations (`capabilities[key] = state`, line 278/285) are visible through `context.capabilities` too. This holds precisely because `sync_selected_context_mirrors` runs at node-selection time (confirmed call sites: `maintenance/ui/window_node_actions.py:194` and `:589`, both inside node-switch/removal flows) strictly before any subsequent scan's `observe_capability` call for that node — selection always precedes data arrival, never the reverse, in both call sites read this session.

  This closes the boundary-table gap: the root-cause hypothesis's step 4 (in this plan's Grounding section) is now proven, not merely asserted.

- [x] **Step 3: Write a failing test that reproduces the hypothesis without any platform mocking of `sys.platform`** (per the spec's ban on treating mocked-platform tests as proof) — construct the scenario directly against real classes. Every symbol below was verified this session against the real source it targets, not guessed:

**Corrected this session — this test must be a `unittest.TestCase`, not bare pytest-style functions.** The original draft used module-level `def test_...():` functions with plain `assert`. This repo has no `pytest` (see Phase 0's correction note) and its actual runner, `python -m unittest discover -s tests`, only discovers test *methods on `unittest.TestCase` subclasses* — a bare module-level function named `test_*` is never collected and would silently never run. Every real test file in `tests/` (e.g. `tests/test_temperature_telemetry.py:41`, `class TemperatureTelemetryTests(unittest.TestCase):`) follows the class-based form; this test now matches it exactly, including reusing the existing `tests.support.models.make_summary` builder instead of constructing `ResourceSummary` by hand (`temperature_telemetry.py`'s own tests do the same):

**Execution correction approved during design review:** the intentional RED proof
uses `tests/thermal_capability_gap_red.py`, which is explicitly runnable but is
not collected by `python3 -m unittest discover -s tests`. Run it with
`python3 -m unittest tests.thermal_capability_gap_red -v`. After Phase 3 turns
the proof green, rename it to `tests/test_thermal_capability_gap.py` so it is a
permanent discovered regression test.

```python
# tests/thermal_capability_gap_red.py
"""Proves TemperatureTelemetry's thermal state resolves out of NO_DATA when a
card is genuinely supported but a sensor never yields a sample (the root
cause of "Waiting for the first sample" persisting forever on platforms with
no exposed sensor, e.g. Apple Silicon SMC or an ACPI-less Windows box)."""

from __future__ import annotations

import unittest

from maintenance.components.temperature import TemperatureState, TemperatureTelemetry
from maintenance.models import CapabilityState
from tests.support.models import make_summary


class ThermalCapabilityGapTests(unittest.TestCase):
    def test_permanently_empty_temperature_samples_never_report_unsupported(
        self,
    ) -> None:
        """A card that is SUPPORTED but never yields a temperature sample must
        eventually surface as thermally UNSUPPORTED, not wait forever."""
        telemetry = TemperatureTelemetry()
        cpu_card = make_summary(
            "cpu", "CPU", capability=CapabilityState.SUPPORTED, temperatures=()
        )
        for _ in range(1000):  # far beyond any reasonable "still waiting" window
            telemetry.record_summary("cpu", cpu_card)
        snapshot = telemetry.series_snapshot("cpu")
        self.assertNotEqual(
            snapshot.state,
            TemperatureState.NO_DATA,
            "thermal state must resolve to a terminal state (unsupported/error), "
            "not remain no_data forever when the card itself is fine",
        )
```

Verified against real source, not guessed: `tests/support/models.py:40-52`'s `make_summary(key, title, *, ..., capability=CapabilityState.UNKNOWN, temperatures=())` builds a real `ResourceSummary` (`maintenance/models.py:43-53`) with explicit overrides, matching the call above field-for-field; `TemperatureTelemetry.series_snapshot(component, *, title=None)` (`maintenance/components/temperature.py:243-245`) accepts a bare `"cpu"` call, defaulting `title` to `component.upper()`, and returns a `TemperatureSeriesSnapshot` whose `.state` field is the real `TemperatureState` enum instance (`maintenance/components/temperature.py:254`), so comparing directly against the enum (not `.value`/a string) matches this repo's own test convention (`tests/test_temperature_telemetry.py:196` does the same, via `self.assertEqual`). `TemperatureState` is a `str, Enum` with members `VALID/NO_DATA/UNSUPPORTED/ERROR` (`maintenance/components/temperature.py:39-43`).

Run it and confirm it **fails** against current code. Read `temperature.py:202-227` (`TemperatureTelemetry.record_summary`) to see exactly why it must fail: the no-samples branch is

```python
else:
    self._settle_inactive_event(telemetry)
    if summary.capability == CapabilityState.UNSUPPORTED:
        telemetry.state = TemperatureState.UNSUPPORTED
    elif summary.failed:
        telemetry.state = TemperatureState.ERROR
    else:
        telemetry.state = TemperatureState.NO_DATA
```

— there is no counter, no timeout, nothing that ever transitions `NO_DATA` to `UNSUPPORTED` purely from repetition; confirmed by reading the full `_ComponentTelemetry` dataclass (`temperature.py:162-178`, `@dataclass(slots=True)`) end to end — its fields are exactly `policy, state, current, history, sensor_histories, events, active_event, last_error, consecutive_hot, cooldown_until`, and grepping the whole file for `empty_reads` (the field Step 2 below adds) returns zero hits today. This is the proof step BugGuard requires before any fix is written.

- [x] **Step 4: Root-cause report**

Write the answer to spec Section 59's 11 questions into `docs/platform_audit/THERMAL-ROOT-CAUSE.md`: what caused it (capability-signal conflation between card-level and thermal-level `CapabilityState`, described above), which boundary (`window_components.py:269-286` writing card capability into the only capability map the Thermals page ever sees, combined with `temperature.py` having no self-terminating no-data state), why prior attempts missed it (all touched acquisition or platform-gating, never the UI capability-signal boundary), and what remains to change (Phase 3).

- [x] **Step 5: Commit**

```bash
git add docs/platform_audit/THERMAL-ROOT-CAUSE.md tests/thermal_capability_gap_red.py
git commit -m "test: prove thermal capability never resolves out of no_data (failing, root cause documented)"
```

---

## Phase 3 — Thermal fix-forward

**Skills:** `BugGuard` Mode A (code-edit validation, full A4 adversarial review — this is exactly the high-risk "unclear evidence" + "cross-file patch" category A4 calls out); `test-driven-development` for every step below; `evolving-apis-and-schemas` because the fix adds a field to `TemperaturePolicy`/`_ComponentTelemetry` that the remote decode path (`maintenance/cluster.py`'s `resource_summary_from_dict`) must keep flowing through unchanged — verified in Step 5 below, not merely assumed; `designing-user-experience` for the empty-state copy (verified already correct in Step 4).

This phase only proceeds once Phase 2's failing test exists and the root cause is confirmed. Do not skip to this phase.

- [x] **Step 1: BugGuard Mode A declaration** — high-risk full-A4 review was declared and recorded in the patch-review artifact.

```text
BugGuard mode: Mode A - code-edit validation
Risk level: high (thermal telemetry shared across local UI, remote nodes, and event detection)
Validator threshold: full A4
Patch-review file: docs/bug_hunts/patch_reviews/PATCH-<today>-001-review.md
Reason: fixes a proven perpetual-wait state without weakening fail-soft or event-detection contracts
```

- [x] **Step 2: Design the smallest correct fix** — `TemperatureTelemetry` now owns a bounded `empty_reads` signal with `TemperaturePolicy.unsupported_confirm_samples`; the additive field and remote propagation were verified, and existing callers remain compatible.

```python
# maintenance/components/temperature.py:57-68 — TemperaturePolicy gains a field
@dataclass(frozen=True, slots=True)
class TemperaturePolicy:
    warning_celsius: float | None = 90.0
    critical_celsius: float | None = 95.0
    recovery_celsius: float | None = 85.0
    consecutive_samples: int = 2
    cooldown_seconds: float = 30.0
    pre_event_samples: int = 4
    post_event_samples: int = 4
    rapid_rise_celsius: float | None = 12.0
    rapid_rise_window: int = 4
    history_limit: int = 600
    event_limit: int = 8
    unsupported_confirm_samples: int = 20  # NEW — consecutive empty reads before NO_DATA -> UNSUPPORTED
```

```python
# maintenance/components/temperature.py:162-178 — _ComponentTelemetry gains a field
# NOTE: this dataclass uses @dataclass(slots=True) (verified this session) — a
# new attribute CANNOT be set at runtime (AttributeError), it must be declared
# here, in slot order, same as every other field on this class.
@dataclass(slots=True)
class _ComponentTelemetry:
    policy: TemperaturePolicy
    state: TemperatureState = TemperatureState.NO_DATA
    current: TemperatureSample | None = None
    history: deque[TemperatureSample] = None  # type: ignore[assignment]
    sensor_histories: dict[str, deque[TemperatureSample]] = None  # type: ignore[assignment]
    events: deque[TemperatureEvent] = None  # type: ignore[assignment]
    active_event: dict[str, Any] | None = None
    last_error: str | None = None
    consecutive_hot: int = 0
    cooldown_until: float = 0.0
    empty_reads: int = 0  # NEW — consecutive record_summary calls with no samples
```

```python
# maintenance/components/temperature.py:202-223 — record_summary's body, full replacement
def record_summary(
    self, component: str, summary: ResourceSummary
) -> TemperatureTelemetryUpdate:
    component = component.casefold()
    telemetry = self._component(component)
    telemetry.last_error = None
    samples = tuple(summary.temperatures)
    if not samples:
        samples = self._legacy_samples(component, summary)

    if samples:
        self._record_samples(telemetry, samples)
        telemetry.state = TemperatureState.VALID
        telemetry.current = samples[-1]
        telemetry.empty_reads = 0
    else:
        self._settle_inactive_event(telemetry)
        if summary.capability == CapabilityState.UNSUPPORTED:
            telemetry.state = TemperatureState.UNSUPPORTED
        elif summary.failed:
            telemetry.state = TemperatureState.ERROR
        else:
            telemetry.empty_reads += 1
            if telemetry.empty_reads >= telemetry.policy.unsupported_confirm_samples:
                telemetry.state = TemperatureState.UNSUPPORTED
            else:
                telemetry.state = TemperatureState.NO_DATA
    return TemperatureTelemetryUpdate(
        component=component,
        snapshot=self.series_snapshot(component, title=summary.title),
    )
```

Everything after `telemetry.last_error = None` down to the final `return` is unchanged from the current method except the three lines marked above (`telemetry.empty_reads = 0` in the samples branch; the `empty_reads` increment-and-check replacing the bare `telemetry.state = TemperatureState.NO_DATA` in the no-samples branch). This keeps the card-level `CapabilityState.SUPPORTED` semantics completely untouched (CPU usage really is supported) while giving the *thermal* series its own authoritative terminal state, without adding a parallel capability map or touching `window_components.py`'s existing per-card logic at all — the smallest boundary fix, made at the one place (`TemperatureTelemetry`) that already owns thermal state transitions.

- [x] **Step 3: Turn Phase 2's failing test green**, then add the adjacent case that must NOT regress — a genuinely slow-but-working sensor must still show "Waiting for the first sample" before the confirm limit:

```python
    # same class as above, ThermalCapabilityGapTests(unittest.TestCase)
    def test_temporarily_slow_sensor_still_waits_before_confirm_limit(self) -> None:
        telemetry = TemperatureTelemetry()
        cpu_card = make_summary(
            "cpu", "CPU", capability=CapabilityState.SUPPORTED, temperatures=()
        )
        telemetry.record_summary("cpu", cpu_card)
        self.assertEqual(
            telemetry.series_snapshot("cpu").state, TemperatureState.NO_DATA
        )
```

Run: `python -m unittest tests.test_thermal_capability_gap -v` — expect both PASS. (Corrected from an earlier `pytest` invocation this plan mistakenly used throughout — this repo has no `pytest` installed; see Phase 0's correction note.)

- [x] **Step 4: Lock in that the empty-state copy is already truthful once this state is reachable** (per `designing-user-experience`) — confirmed this session at `maintenance/ui/thermal_graph.py:175`: `if snapshot.state is TemperatureState.UNSUPPORTED: self._draw_empty(canvas, width, height, "Temperature not supported")`. This is user-visible for supported battery telemetry; CPU/GPU/Storage unsupported series are removed by the existing `_should_show` gate and use the page-level no-supported-sensors message. `tests/test_telemetry_graph.py` now covers the unsupported rendering path:

```python
# tests/test_telemetry_graph.py — new test, same class as the others
def test_unsupported_state_draws_truthful_placeholder(self) -> None:
    graph = self._graph()
    graph._snapshot = TemperatureSeriesSnapshot(
        component="cpu",
        title="CPU Temperature",
        state=TemperatureState.UNSUPPORTED,
        current_celsius=None,
        minimum_celsius=None,
        maximum_celsius=None,
        warning_celsius=90.0,
        critical_celsius=95.0,
        samples=(),
        events=(),
    )

    graph._redraw()

    graph._canvas.create_text.assert_called()
    self.assertEqual(
        graph._state_label.config.call_args.kwargs["text"],
        "Temperature not supported",
    )
```

Verified this session, not inferred: `_draw_empty` updates both the state label and canvas text. The characterization test passed, then temporarily changing the message made it fail for the expected copy mismatch; the production string was restored. This locks the truthful battery-visible placeholder without changing rendering behavior.

- [x] **Step 5: Check remote-node propagation** (per `evolving-apis-and-schemas`) — traced this session, not assumed; the earlier draft of this plan cited the wrong files (`remote_support/protocol.py` / `components/node_context.py` — grepped both this session for `telemetry`/`record_summary`/`ResourceSummary`/`temperatures`, zero hits in either). The real path is:
  1. `maintenance/cluster.py:178-219` (`resource_summary_from_dict`) decodes a remote wire payload back into a real `ResourceSummary`, including `capability` (via `CapabilityState(...)`, line 188) and `temperatures` (via `temperature_sample_from_dict`, defined at `maintenance/components/temperature.py:560`, called per-item at `cluster.py:212-217`) — this is the same `ResourceSummary`/`TemperatureSample` classes the local scan path produces, not a parallel shape.
  2. `maintenance/ui/window_presentation.py:13-33` (`show_snapshot`) is the single application point for any full snapshot — local or remote — and its `for resource in snapshot.resources: controller._observe_capability(resource.key, resource); controller._record_thermal_summary(resource.key, resource)` loop (lines 31-33) is unconditional on node origin.
  3. `controller._record_thermal_summary` → `record_thermal_summary` (`maintenance/ui/window_components.py:212-217`) → `context.telemetry.record_summary(key, resource)`, where `context = controller._selected_context()` — the exact same `TemperatureTelemetry.record_summary` this phase is patching.

  So the fix in Step 2 already covers remote nodes with zero additional code — a remote peer's decoded `ResourceSummary` flows through the identical `record_summary` call. No second implementation is needed. If a future audit finds a decode path that bypasses `resource_summary_from_dict`/`show_snapshot` (e.g. a partial/incremental update path not yet checked this session), that is a new finding for `docs/bug_hunts/`, not something to silently patch here.

- [x] **Step 6: A4 adversarial review**

Run BugGuard's full A4 (or the portable independent-review fallback per `BugGuard`'s own fallback rules) against this patch. Required checks: does the confirm-limit fix ever suppress a real, valid late-arriving sample (no — `empty_reads` resets to 0 the moment `samples` is non-empty, confirmed in Step 2's snippet); does it change behavior for any platform where sensors already work today, i.e., Linux (no — `empty_reads` only increments on the *no-samples* branch, which a working Linux sensor never takes); does it interact with `_settle_inactive_event`/event detection (no — that call is unchanged, made before the new counter logic).

- [x] **Step 7: Linux regression check**

```bash
python -m unittest tests.test_thermal_card tests.test_thermals_page tests.test_temperature_telemetry tests.test_telemetry_graph -v
```

All must pass unchanged in behavior (same assertions, same outcomes) — if any Linux-path assertion needs to change, that is a regression and must be treated as a new BugGuard finding, not silently accepted.

- [x] **Step 8: Commit**

```bash
git add maintenance/components/temperature.py tests/test_thermal_capability_gap.py tests/test_telemetry_graph.py docs/bug_hunts/patch_reviews/
git commit -m "fix: resolve thermal telemetry out of permanent no_data when a card is supported but never yields a sample"
```

---

## Phase 4 — Per-subsystem audits (CPU, Memory, Storage, GPU, Network, Battery, Downloads/Trash)

**Skills:** `BugGuard` Mode B for each subsystem audit; `dispatching-parallel-agents` because these seven audits share no state and can run concurrently; `designing-user-experience` for any empty/unsupported-state copy fixes found along the way; `evolving-apis-and-schemas` only if a fix changes `ResourceSummary` shape.

- [x] **Step 1: Dispatch one independent audit per subsystem**, each following the same BugGuard Mode B checklist (read the real acquisition code for all three platforms, classify per capability state, do not use "supported" for a bare conditional branch). Every citation below was re-verified this session against real source — two were corrected from the earlier draft (marked below):

  - **CPU** — *corrected citation*: `psutil.cpu_freq()` is called in `maintenance/scanner.py:312` (`SystemScanner.scan_component`), not `dashboard.py` as the earlier draft said. The fail-soft handling of a `None`/zero/reversed reading lives in `maintenance/scanner_support/dashboard.py:432-451` (`_frequency_detail`, a `@staticmethod` whose own docstring states "Missing, zero, or reversed min/max fields are tolerated"). This is **already fully tested** — `tests/test_maintenance.py:878-914` covers all four cases (`test_frequency_detail_shows_current_and_max`, `_omits_zero_or_missing_max`, `_reports_unavailable_for_missing_current`, `_tolerates_reversed_max`). No new test needed; Step 1's job here is to confirm this coverage still exists and still passes, not to write it.
  - **Memory** — swap/zram accounting confirmed real at `maintenance/scanner_support/dashboard.py:453` (`_memory_resource`) and `:507-532` (`_is_zram_device`/`_swap_details`, zram detected by `name.startswith("/dev/zram")`) — Linux-specific by design (zram is a Linux kernel feature), not something Windows/macOS should be made to emulate; confirm Windows/macOS swap is reported through the same `swap_memory()` fields without a fabricated "zram" label.
  - **Storage** — `storage.py` (already read this session — Trash size branches are real; re-verify `_windows_trash_size` against a Windows fixture, since `SHQueryRecycleBinW` requires `windows_windll()` from `maintenance/components/scan_support.py:57` to actually resolve on Windows (confirmed defined there; also imported at `storage.py:16` and `downloads.py:31`), which cannot be proven from Linux — mark `NOT_VERIFIED_ON_NATIVE_PLATFORM` until Phase 13).
  - **GPU** — `gpu.py` probe function names confirmed exactly: `_mac_gpu_probe` (line 263), `_windows_gpu_probe` (line 308), `_linux_gpu_probe` (line 335), dispatched via `mac_loader`/`windows_loader`/`linux_loader` at lines 158-162 — verify their utilization/memory fields are never fabricated when the provider can't supply them (spec Section 20/42's "one unavailable GPU metric must not break identity/detail rendering").
  - **Network** — *already verified correct, not a suspected bug*: `TUNNEL_INTERFACE_PREFIXES` (`maintenance/scanner.py:138-140`) is `frozenset({"tun", "tap", "utun", "ppp", "ipsec", "wg"})` — `utun` (the actual macOS tunnel-interface prefix) is already included, so this is not a Linux-only assumption as the earlier draft speculated. The genuine gap is test coverage, not the classification logic: `tests/test_network_card.py:160-205` (`VpnDetectionTests`) tests `tun0`/`eth0`/`wlan0` thoroughly but has zero references to `utun` anywhere in the test suite (confirmed by grep). Add one test, following that class's exact existing pattern:

    ```python
    # tests/test_network_card.py — new case in VpnDetectionTests
    def test_vpn_interface_detects_macos_utun_prefix(self) -> None:
        fake = SimpleNamespace(
            net_if_stats=lambda: {
                "en0": SimpleNamespace(isup=True),
                "utun3": SimpleNamespace(isup=True),
            },
        )

        self.assertEqual(SystemScanner._vpn_interface(fake), "utun3")
    ```

    This is a characterization test locking in already-correct behavior (should pass immediately) — per `test-driven-development`'s guidance for this case, confirm it isn't a false-positive by temporarily removing `"utun"` from `TUNNEL_INTERFACE_PREFIXES` and checking the test then fails, before trusting it as a permanent regression guard.
  - **Battery** — confirmed real at `maintenance/scanner_support/dashboard.py:771,1016,1026`: a no-battery machine (`psutil.sensors_battery()` returning `None`, documented at line 1064) produces `CapabilityState.UNSUPPORTED`, not an exception. Confirm that battery *temperature* absence is covered by the Phase 3 fix (`empty_reads` confirm-limit) since `battery` shares `TemperaturePolicy`/`TemperatureTelemetry` — this is a verification step, not new work, once Phase 3 lands.
  - **Downloads/Trash**: `downloads.py`'s `DownloadsPathResolver` — verify the OneDrive-redirect and sentinel-fallback paths (already read this session) against Windows path-length/permission edge cases; confirm cleanup never widens beyond the resolved root (`os.path` containment check).

- [x] **Step 2: Log every proven defect** to `docs/bug_hunts/bugs_found_N.md` per BugGuard's ledger format; do not fix inside this phase's audit sub-tasks — split any fix into its own Mode A task following Phase 3's pattern (declaration → failing test → smallest fix → A4 review → Linux regression → commit). The `utun` test above is an exception (a pure characterization test with no fix attached) and may be added directly. No Phase 4 production defect met the proof threshold; needs-more-evidence follow-ups are recorded in `docs/platform_audit/PLATFORM-MATRIX.md`.

- [x] **Step 3: Update the platform matrix**

Add a row per capability to `docs/platform_audit/PLATFORM-MATRIX.md` using only `VERIFIED / IMPLEMENTED BUT NOT NATIVE-VERIFIED / PARTIAL / UNSUPPORTED BY CURRENT PROVIDER / BROKEN / NOT APPLICABLE`.

---

## Phase 5 — Process review and termination

**Skills:** `BugGuard` Mode B for the audit, Mode D for anything touching the termination safety boundary (process kill/force-quit is exactly BugGuard's own "high-risk surface" list), Mode A only if a proven defect requires a scoped fix.

- [x] **Step 1: Audit two files with distinct responsibilities** — *corrected from the earlier draft, which cited only one*: `maintenance/components/process_safety.py` owns the *safety policy* (whether a process may be touched at all), not termination mechanics. Confirmed by reading it this session: `normalize_username`/`usernames_match` (lines 44-75) already strip Windows `DOMAIN\username` prefixes before comparing — genuinely cross-platform-aware, not a Linux assumption; `is_protected_process_name`/`protected_process_pids` (lines 52, 78) and `ProcessSafetyPolicy` (line 98) decide protection, but the file contains no `.terminate()`/`.kill()` call at all (confirmed by grep). The actual termination mechanics live in `maintenance/actions.py:28` (`ProcessManager` — this is the "canonical `ProcessManager` safety owner" the original spec's Section 24 refers to): `request_quit`/`terminate` call `process.terminate()` (line 44), `force_quit` calls `process.kill()` (line 78), both via `psutil.Process` methods. Audit both files together — platform differences in: process username resolution and executable path resolution (`process_safety.py`), protected/system process detection (`process_safety.py`), and termination semantics — graceful vs force, wait, already-exited, access-denied (`actions.py`'s `ProcessManager._run_process_action`, which this session's read shows delegates entirely to `psutil.Process.terminate()`/`.kill()` — confirm psutil's own Windows-vs-POSIX abstraction is trusted here rather than re-implemented, since no `sys.platform`/`os.name` branch exists in either file).
- [x] **Step 2: Declare BugGuard Mode D** for the termination-safety surface specifically (`docs/security_reviews/SEC-20260912-001-review.md`), per its own trigger ("auth/... admin" and process-safety surfaces qualify as full D7). Do not weaken protection to make a Windows/macOS path "pass."
- [x] **Step 3:** Log findings to the bug ledger; no vulnerability met the ledger threshold. The ancestry divergence was recorded in the Mode D review as a hardening opportunity and fixed through the scoped Mode A patch `44a0801`; no public action signatures changed.

---

## Phase 6 — Config/log paths, subprocess, encoding, filesystem paths

**Skill:** `BugGuard` Mode B for the audit; `consolidating-responsibilities` before writing any new path-resolution helper (search `maintenance/preferences.py`, `maintenance/persistence.py`, `maintenance/scanner_support/paths.py` first — these likely already own this).

- [x] **Step 1: Read `maintenance/preferences.py` and `maintenance/scanner_support/paths.py` in full and confirm centralization** — `PathsMixin` is a Downloads-path delegation shim, while `default_preferences_path` owns platform-specific configuration paths. The audit found and fixed the logging inconsistency: `main.default_log_path` now selects XDG state on Linux, `~/Library/Logs` on macOS, and `LOCALAPPDATA`/`APPDATA` or its standard fallback on Windows, with deterministic injectable inputs and regression coverage.
- [x] **Step 2: Audit every `subprocess.run`/`subprocess.Popen` call** — the six application call sites were inventoried. Existing GPU/dashboard calls already suppress Windows console creation; the direct TLS `openssl` call now forwards the same platform-appropriate `CREATE_NO_WINDOW` flag. No `shell=True` usage exists. OpenSSL absence remains an explicit command failure at the existing caller boundary rather than a silent fallback.
- [x] **Step 3:** Audit decode/encoding. `run_text_command` now catches `UnicodeError` at the shared decode boundary and returns the established fail-soft error tuple; regression coverage exercises a non-UTF-8 decode failure.
- [x] **Step 4:** Findings were fixed through the scoped Mode A changes in `0fb9518`; no shell execution was introduced and no public command/path contracts changed.

---

## Phase 7 — Tk/UI compatibility and Thermals-page UI matrix

**Skills:** `BugGuard` Mode B for correctness findings (hands them off, doesn't fix UI logic itself); `UI` for the rendered-widget audit (resize, DPI, ttk style properties, scrollbar/dialog/focus behavior across platforms); `building-accessible-interfaces` for keyboard/focus/contrast on the Thermals page and any dialog touched; `reviewing-interface-quality` as the closing gate.

- [x] **Step 1: Run the `UI` skill's surface-evidence pipeline** against the Thermals page, shared graph, dashboard composition, and dialogs. Structural evidence is recorded in `.ui/`; Tkinter has no browser DOM/axe path. The available Linux Tk render/resize surface passed; native Windows/macOS rendering remains unverified.
- [x] **Step 2: Run `building-accessible-interfaces`** against focus-back and the scrollable content area. The page retains native ttk buttons/scrollbars and explicit back-button focus. The confirmed color-only threshold distinction was fixed with a distinct critical `(8, 4)` dash pattern; evidence and limitations are recorded in `.ui/reports/`.
- [x] **Step 3: Re-run the exact Thermals behavioral matrix from the spec**: supported/unsupported state, first samples, bounded history, retained page state, node-aware render preparation, and resize coverage passed through the focused, node, and live-Tk tests. No graph-specific polling was introduced.
- [x] **Step 4: Run `reviewing-interface-quality`** as the closing gate. The independent opposition report is recorded at `.ui/reports/ui-opposition-report.md`; no blocker was found.
- [x] **Step 5:** The correctness/accessibility finding was fixed through the scoped Mode A change; UI evidence and validation reports are recorded under `.ui/`.

---

## Phase 8 — Discovery, remote listener/TLS, node identity

**Skills:** `BugGuard` Mode D (mandatory — this is exactly the "OAuth/email/provider integrations... fail-open/fail-closed" full-D7 category) for the security-relevant surfaces; `evolving-apis-and-schemas` for anything in `maintenance/remote_support/protocol.py`.

- [x] **Step 1: Audit `maintenance/components/discovery_session.py` / `network_discovery.py`** for Zeroconf/mDNS lifecycle differences across platforms. Discovery callbacks are locked and lifecycle/generation gated; manual endpoint fallback remains; no subnet-scanning fallback exists. Native Windows/macOS transport behavior remains unverified.
- [x] **Step 2: Declare BugGuard Mode D** for `maintenance/remote_support/server.py`, `transport.py`, and `maintenance/remote_security.py` (TLS/certificate/fingerprint logic). Full D7 used all three mandatory packs, four independent opposition legs, and Agent 5; evidence is recorded in `SEC-20260912-002-review.md`.
- [x] **Step 3: Node identity stability —** persisted stable peer IDs are independent of display name, hostname, address, and selector position; identity and transport fingerprint mismatches fail closed. Remote generation and pairing paths were included in the full D7 evidence.
- [x] **Step 4:** No vulnerability was proven, so no Mode B transition is required. Hardening/documentation follow-ups are recorded as residual risk; no Phase 8 app-code patch is needed.

---

## Phase 9 — Packaging, installers, Python version

**Skill:** `BugGuard` Mode B for the audit (this is explicitly "do not redesign distribution in this pass" per the original spec — audit and smallest-fix only).

- [x] **Step 1: Audit `pyproject.toml`** — `requires-python = ">=3.10"` is achievable. The conditional NVIDIA dependency excludes Darwin, both console entry points are declared, package data includes `py.typed`, and a repository-wide compile plus Ruff `--target-version py310` check found no Python 3.11+-only syntax/API pattern in application or test sources.
- [x] **Step 2: Audit `install/*.ps1` vs `install/*.sh`** — all eight named installer commands (`build`, `install`, `install-online`, `install-user`, `rollback`, `uninstall`, `upgrade`, `verify`) have paired scripts, with `_common` helpers in both families. Tests and source inspection confirm the same wheel/entry-point surface, version floor checks, verification, PATH handling, and the three previously recorded fixes remain intact. Native PowerShell execution was unavailable and is not claimed.
- [x] **Step 3: Log findings; no packaging redesign.** No Phase 9 defect was found. Packaging is verified by repository tests and Linux shell checks; Windows PowerShell and clean native Python 3.10/3.11 installation remain platform evidence gaps only.

---

## Phase 10 — Canonical reuse audit

**Skill:** `consolidating-responsibilities`, run once against every fix produced by Phases 3–9 collectively (not per-phase) since its value is in catching duplication *across* the fixes just made.

- [x] **Step 1:** Audited every helper/function introduced or changed in Phases 3–9 against repository-wide owners. `TemperatureTelemetry` owns thermal-state normalization; `external_commands.run_text_command`/`run_json_command` own generic command execution and are reused by acquisition callers; `protected_process_pid_snapshot` extends the existing process-safety owner; identity and certificate fingerprint functions remain in `nodes.py`/`remote_security.py` where their trust semantics belong.
- [x] **Step 2:** No `windows_utils.py`, `mac_utils.py`, or generic `platform_helpers.py` dumping-ground module was created. Platform acquisition remains in `scanner_support/*`; normalization remains in component owners.
- [x] **Step 3:** No Phase 3–9 duplication justified a refactor or BugGuard candidate. The two `_hash_fingerprint` methods in `scanner.py` and `components/downloads.py` are pre-existing domain-specific implementations outside the audited fixes; remote TLS material generation intentionally remains separate from generic command execution because it owns certificate-file lifecycle and secret handling. No application code changed in Phase 10.

---

## Phase 11 — Fail-soft, performance, shutdown

**Skills:** `BugGuard` Mode C only if a genuine performance regression is found; `investigating-performance` as the generic diagnostic method for confirming or ruling one out.

- [x] **Step 1:** Diff audit found no new `threading.Thread`, `after` polling loop, timer-per-graph, or render-path subprocess spawn in Phases 3–9. Thermal confirmation is a bounded counter in existing telemetry state; UI threshold styling is draw-time geometry only.
- [x] **Step 2:** No new external-command cost or acquisition path was introduced. Phase 6 only forwards Windows `CREATE_NO_WINDOW` to existing commands, including the existing TLS-material command; the existing temperature cache cadence is unchanged. `investigating-performance` was therefore not required.
- [x] **Step 3:** Existing lifecycle coverage confirms cancellation, coordinator shutdown, discovery close/cancel, stale callback rejection after close, and window shutdown. No changed Phase 3–9 path creates an orphan subprocess/thread or an unguarded Tk callback.

---

## Phase 12 — Behavior tests: first-sample transition, unsupported state, node switching

**Skill:** `test-driven-development` (these are pure behavior tests, platform-independent, written directly against the normalized contract — no `sys.platform` mocking, per the spec's explicit ban on treating that as proof). Every RED test below must be run and confirmed failing for the stated reason before Phase 3 (or the relevant Phase 4–9 fix) makes it GREEN — do not write these and mark them done without watching them fail first.

- [x] **Step 1: First-sample-transition and confirm-limit-to-`UNSUPPORTED` — already written in Phase 2/3, verified**

`tests/test_thermal_capability_gap.py` (renamed from the Phase 2 RED module after
Phase 3 turns it green) is this permanent regression test:

```python
class ThermalCapabilityGapTests(unittest.TestCase):
    def test_permanently_empty_temperature_samples_never_report_unsupported(self) -> None:
        ...  # RED against current code, GREEN after Phase 3's empty_reads counter
```

No new test needed here for this case. Re-run it explicitly at Phase 12 time to confirm it is still GREEN after Phase 4–9 touched other components:

```bash
python -m unittest tests.test_thermal_capability_gap -v
```

- [x] **Step 2: Immediate-`UNSUPPORTED` path — already GREEN, characterization only, no RED cycle needed**

Confirmed this session: `tests/test_temperature_telemetry.py:190-196` already asserts `summary.capability == CapabilityState.UNSUPPORTED` → `snapshot.state == TemperatureState.UNSUPPORTED` immediately (no confirm-limit wait needed when a provider *authoritatively* declares absence, e.g. no-battery desktop, GPU probe returning `UNSUPPORTED`). This is existing, already-passing coverage — spec Section 51's requirement is already met for this path. Do not duplicate it. Only add a fixture-driven variant if a Phase 4–9 audit finds a provider (e.g. `gpu.py`'s `_mac_gpu_probe`) that can return "no GPU" without setting `capability=CapabilityState.UNSUPPORTED` on the resource — that would be a genuine new finding, logged to `docs/bug_hunts/`, not silently patched here.

- [x] **Step 3: Node-isolation regression test — added and verified**

Confirmed by reading `maintenance/nodes.py:675` (`NodeContext.telemetry: TemperatureTelemetry = field(default_factory=TemperatureTelemetry)`): each node context gets its own telemetry instance by construction, so isolation should already hold — but nothing in `tests/test_window_nodes.py` or `tests/test_node_selection.py` (grepped this session — neither references `telemetry` or asserts cross-node isolation) actually proves it, and `thermal_render_state`/`refresh_thermals_page` in `maintenance/ui/window_components.py:220-242` read whatever `controller._selected_context()` currently returns. A future refactor that hoists `telemetry` onto the controller instead of the context would silently reintroduce cross-node leakage with no test catching it. Write this as a real RED test now, using the existing `tests/support/nodes.py` builders:

```python
# tests/test_thermal_node_isolation.py
"""Proves per-node thermal telemetry isolation survives the real selection
path (window._selected_context() -> NodeSelection -> NodeRegistry.context()),
not just object construction — a regression guard against a future refactor
that hoists telemetry onto the controller instead of the per-node context."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from maintenance.components.temperature import TemperatureSample
from maintenance.models import CapabilityState
from maintenance.nodes import NodeRegistry
from maintenance.ui.window_components import thermal_render_state
from tests.support.models import make_summary
from tests.support.nodes import make_local_context, make_remote_context
from tests.support.window import make_window as make_bare_window


class ThermalNodeIsolationTests(unittest.TestCase):
    def test_switching_selected_node_does_not_leak_thermal_history(self) -> None:
        window = make_bare_window()
        registry = NodeRegistry()
        local_ctx = make_local_context()
        remote_ctx = make_remote_context("peer-a")
        registry.register_context(local_ctx)
        registry.register_context(remote_ctx)
        registry.select(local_ctx.node_id)
        window._node_registry = registry
        window._selected_node_id = registry.selected_id()

        sample = TemperatureSample(
            component="cpu", sensor_id="cpu0", sensor_name="cpu0",
            value_celsius=55.0,
            sampled_at=datetime.now(timezone.utc),
            sampled_monotonic=0.0,
        )
        local_ctx.telemetry.record_summary(
            "cpu",
            make_summary("cpu", "CPU", capability=CapabilityState.SUPPORTED,
                          temperatures=(sample,)),
        )

        window._selected_node_id = remote_ctx.node_id
        remote_context = window._selected_context()
        self.assertIs(remote_context, remote_ctx)
        remote_state = thermal_render_state(window, remote_context)
        remote_cpu = remote_state.series_for("cpu")
        self.assertTrue(
            remote_cpu is None or not remote_cpu.samples,
            "remote node's thermal series must be empty/absent, not inherit "
            "the 55.0C sample just recorded against the local node's telemetry",
        )

        window._selected_node_id = local_ctx.node_id
        local_context = window._selected_context()
        self.assertIs(local_context, local_ctx)
        local_state = thermal_render_state(window, local_context)
        local_cpu = local_state.series_for("cpu")
        self.assertTrue(
            local_cpu is not None and local_cpu.samples,
            "switching back to the local node must restore its own history, "
            "not show an empty/reset graph",
        )
```

Verified this session against real source, not guessed (and, per the earlier `unittest` correction, rewritten from a bare pytest-style function into a `unittest.TestCase` method, matching this repo's actual test runner): `NodeContext` is a plain mutable `@dataclass` (`maintenance/nodes.py:656`); `NodeRegistry.register_context`/`.select`/`.selected_id`/`.context` are the exact methods `tests/test_window_nodes.py`'s own `_make_window` helper uses (confirmed at `tests/test_window_nodes.py:117-123`); `window._selected_context()` (`window.py:271-272`) resolves through `ui_node_runtime.selected_context` → `NodeSelection.selected_context()` (`maintenance/components/node_selection.py:39-45`), which only reads `self._registry.context(self._selected_id())` — the other callables `NodeSelection` takes (`cancel_active_scan`, `sync_selected_context`, etc.) are captured as lazy lambdas at construction and never invoked by a plain read, so `make_bare_window()` needs no extra mocking for this test; `TemperatureSample`'s exact fields are `component, sensor_id, sensor_name, value_celsius, sampled_at, sampled_monotonic` (`maintenance/components/temperature.py:47-53`); `make_summary`'s exact keyword names are confirmed at `tests/support/models.py:40-52`. This is real, checked code — run it as written, not adapted, and if it fails on an import or attribute name at execution time (APIs can drift between when this plan was written and when it's executed), fix the plan's citation, don't paper over it in the test.

If this test passes immediately, that is expected here (unlike Phase 2/3's bug-proving test) — this is a **characterization test** locking in already-correct isolation-by-construction, not a bug hunt. The required false-positive check was performed by temporarily hardcoding `thermal_render_state` to always read the local node; the test failed with the remote-history assertion, and the production function was restored unchanged.

```bash
python -m unittest tests.test_thermal_node_isolation -v
```

- [x] **Step 4: Commit**

```bash
git add tests/test_thermal_node_isolation.py
git commit -m "test: lock in per-node thermal telemetry isolation"
```

---

## Phase 13 — Native smoke tests (Windows / macOS / Linux regression)

**Skill:** `verifying-before-completion` — mandatory before any platform is marked `VERIFIED` rather than `IMPLEMENTED BUT NOT NATIVE-VERIFIED`.

- [x] **Step 1: Windows native smoke matrix** — unavailable; no Windows machine/VM or PowerShell executable exists in this environment. No native verification is claimed.
- [x] **Step 2: macOS native smoke matrix** — unavailable; no macOS host exists in this environment. No native verification is claimed.
- [x] **Step 3: Native evidence classification** — Windows/macOS and clean Python 3.10/3.11 installation cells remain `IMPLEMENTED BUT NOT NATIVE-VERIFIED`, consistent with the existing capability-transparency vocabulary.
- [x] **Step 4: Linux regression, mandatory regardless of Windows/macOS availability** — `1377/1377` tests passed; `ruff check .` passed. Repository-wide format, Pyright, and Mypy findings remain documented baseline/tooling issues and are not represented as passes.

```bash
python -m unittest discover -s tests -q
ruff check . && ruff format --check . && pyright && mypy --ignore-missing-imports .
```

Compare against Phase 0's baseline log — any new failure is a regression and must be fixed before this phase closes.

---

## Phase 14 — Documentation and final report

**Skills:** `repo-context-curator` for folding the durable lesson back into repo context; `verifying-before-completion` for the final validation claims.

- [x] **Step 1: Update `docs/CAPABILITY_TRANSPARENCY_2026-09-10.md`** (or supersede it with a dated new version per that doc's own convention) to reflect Phase 3's fix and every Phase 4–9 finding — using only the existing state vocabulary, no "fully compatible" language.
- [x] **Step 2: Invoke `repo-context-curator`** to check whether `AGENTS.md` needs the thermal-capability-conflation lesson (a distinct thermal-capability signal vs. card-level capability) folded in as durable guidance, so a ninth thermal fix attempt doesn't re-make the same mistake.
- [x] **Step 3: Write the final report** answering every question in the original spec's Section 61 (repo areas audited, defects found per platform, root cause, fixes made, canonical reuse, native evidence gaps, exact commands run, remaining unsupported capabilities, files changed, working-tree status) into `docs/platform_audit/PLATFORM-MATRIX.md`'s closing section.
- [x] **Step 4: Final validation, per `verifying-before-completion`** — re-run every command from Phase 0 Step 2 and Phase 13 Step 4, paste the actual output, and only then close the pass.

---

## Self-Review

**Spec coverage:** Every numbered section (1–61) of the original audit spec maps to a phase above: baseline→0, matrix→1&4, assumptions→1, thermal trace/proof→2, thermal fix→3, per-subsystem (CPU/Mem/Storage/GPU/Net/Battery/Downloads/Trash)→4, process→5, config/log/subprocess/encoding/paths→6, Tk/UI/Thermals-UI→7, discovery/remote/TLS/identity→8, packaging/installers/Python version→9, canonical reuse/boundaries→10, fail-soft/perf/shutdown→11, behavior tests→12, native smoke+Linux regression→13, docs+final report→14.

**Placeholder scan:** No "TBD"/"add appropriate error handling" language used; every audit step names exact files/commands; the one illustrative code fix (Phase 3) is real code against real classes read this session, not a stub — but it is explicitly gated behind "prove first" per Phase 2's failing test, consistent with BugGuard's non-negotiable rules.

**Type/name consistency:** `TemperatureState`, `CapabilityState`, `TemperatureTelemetry`, `ResourceSummary`, `TemperaturePolicy` are used consistently with their real definitions in `maintenance/models.py` and `maintenance/components/temperature.py` throughout.

**Scope check:** This is one continuous audit-and-fix-forward pass over one existing application, not multiple independent subsystems needing separate specs — it was not decomposed further, matching the user's framing of it as a single phase.

## Execution Handoff

Plan complete and saved to `docs/plans/2026-09-12-cross-platform-compat-audit.md`. Two execution options:

1. **Subagent-Driven (recommended)** — dispatch a fresh sub-agent per task using the Agent tool, invoking the exact skill named for that task, with review between tasks.
2. **Inline Execution** — execute tasks in this session using `executing-plans`, batch execution with checkpoints for review.

Which approach?
