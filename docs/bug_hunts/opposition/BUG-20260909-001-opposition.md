# Opposition Review - BUG-20260909-001

**Candidate bug:** BUG-20260909-001
**Created:** 2026-09-09
**Current cycle:** 1 / 3
**Candidate entry source:** `docs/bug_hunts/bugs_found.md#bug-20260909-001---component-edge-case-audit`

## Artifact ownership

The main auditor owns the scaffold and final synthesis. Each selected reviewer
owns only its section and must write directly into this file. Agent 5 owns only
its section. No reviewer section may be backfilled.

## Candidate summary

This is a broad, read-only audit of the old `window.py`/facade behavior and new
component subsystem, including UI, preferences, discovery, actions, and
packaging boundaries. Discovery produced these hypotheses requiring opposition:

1. Zeroconf transport callbacks mutate peer maps concurrently with expiry.
2. Node permission toggles replace unrelated permissions.
3. Node-colour persistence failure rolls back to `None`, not the old colour.
4. Invalid UTF-8 store files escape the documented startup fallback.
5. Manual node ports accept values outside the valid TCP range.
6. Thermal thresholds can be plotted outside the visible graph.
7. TypeError-text legacy fallback can repeat a partially executed operation.
8. Process PID reuse and cleanup filesystem races may undermine destructive-action safety.
9. PowerShell online reinstall may preserve stale same-version files.
10. Dashboard cards or node controls may lack keyboard/narrow-width accessibility.

Each concern must be classified independently as validated, downgraded,
disproven, accepted risk, or needs more evidence. A spark is not a bug without
a reachable path, violated contract, impact, and reproducible evidence.

## Evidence index

- `window.py`, `algo.py`
- `maintenance/components/`
- `maintenance/actions.py`, `maintenance/persistence.py`, `maintenance/preferences.py`, `maintenance/cluster.py`
- `maintenance/ui/`, `maintenance/dialogs.py`
- `maintenance/remote.py`
- `install/`
- `tests/`
- prior patch reviews `PATCH-20260909-003` through `PATCH-20260909-008`
- `docs/window-extraction-plan.md`

## Baseline validation

- Full repository tests: passed, 978 tests.
- Ruff, format, Pyright, Mypy, and diff checks: passed.
- `./lr --list`, `./lr impact`, `./lr 7`, `./lr secrets`: unavailable because no `./lr` executable exists.

## Selected threshold

Full B7 is required because the candidate set includes P1/P2 destructive,
cross-thread, persistence, network, and UI/runtime-boundary concerns.

Required independent reviewers:

- Opposing Agent 1 - Reproduction Skeptic
- Opposing Agent 2 - Repo-Truth Skeptic
- Opposing Agent 3 - Architecture/Security Skeptic
- Opposing Agent 4 - External-Research Skeptic
- Agent 5 after all four sections complete

## Cycle 1 Opposition

### Opposing Agent 1 - Reproduction Skeptic

**Review scope:** Independent reproduction review of all ten candidate hypotheses.
No other opposition sections were read. App code and normal repository tests were
not changed. One independent counter-test was added at
`docs/bug_hunts/poc/BUG-20260909-001/agent1_counter_test.py`.

**Counter-test hygiene gate:**

- **Command:** `ruff check docs/bug_hunts/poc/BUG-20260909-001/agent1_counter_test.py && ruff format --check docs/bug_hunts/poc/BUG-20260909-001/agent1_counter_test.py && pyright docs/bug_hunts/poc/BUG-20260909-001/agent1_counter_test.py && mypy --ignore-missing-imports docs/bug_hunts/poc/BUG-20260909-001/agent1_counter_test.py`
- **Input:** The independent counter-test file.
- **Output:** Ruff passed; format reported `1 file already formatted`; Pyright reported `0 errors`; Mypy reported `Success: no issues found`.
- **Interpretation:** The counter-test was check-clean before its result was counted.
- **Verdict:** Pass; evidence eligible.

## Reproduction Attempts

### 1. Zeroconf callback and expiry concurrency

- **Command:** `PYTHONPATH=. python - <<'PY' ...` (two threads, 10,000 update callbacks and 10,000 `expire_stale(2)` calls against one synthetic peer).
- **Input:** Injected backend, valid peer record, TTL zero, concurrent map mutation paths.
- **Output:** `discovery concurrent stress: no RuntimeError peers=1`.
- **Interpretation:** This stress run did not expose a dictionary-iteration exception or corrupted observable state. The implementation has no lock and Zeroconf callbacks can be concurrent with expiry, so the race remains plausible; this is not a disproval.
- **Verdict:** Still plausible, not reproduced in this environment.

### 2. Permission toggle replaces unrelated permissions

- **Command:** `PYTHONPATH=. python - <<'PY' ...` invoking `AppWindow._set_node_permissions` with an existing `READ_PERMISSIONS` set and only `process_review` selected.
- **Input:** Existing permissions: `dashboard_read`, `component_read`, `process_review`, `storage_review`; requested UI set: `{process_review}`; save succeeds.
- **Output:** `permissions after one UI toggle: ['process_review']`; `permissions removed: ['component_read', 'dashboard_read', 'storage_review']`.
- **Interpretation:** The reachable controller path constructs a complete permission set from the three process checkboxes and replaces the record, dropping unrelated permissions.
- **Verdict:** Reproduced; strong candidate for a validated bug.

### 3. Color persistence failure rolls back to `None`

- **Command:** `PYTHONPATH=. python - <<'PY' ...` invoking `AppWindow._set_node_color` with a fake registry and forced `_save_cluster_state` failure.
- **Input:** Existing descriptor/record color `rose`; requested color `indigo`; persistence returns `False`.
- **Output:** `color rollback: None`.
- **Interpretation:** The failure branch hardcodes `registry.set_color(..., None)` rather than restoring the prior color.
- **Verdict:** Reproduced; strong candidate for a validated bug.

### 4. Invalid UTF-8 store files escape startup fallback

- **Command:** `PYTHONPATH=. python docs/bug_hunts/poc/BUG-20260909-001/invalid_store_encoding_poc.py`.
- **Input:** One-byte invalid UTF-8 file `b"\\xff"` for each store.
- **Output:** `FAIL: PreferencesStore.load escaped UnicodeDecodeError`; `FAIL: ClusterStore.load escaped UnicodeDecodeError`; process exited with `RuntimeError`.
- **Interpretation:** `read_text_or_none` catches `OSError` but not `UnicodeDecodeError`, despite both store contracts saying unreadable/malformed files fall back and must not block startup.
- **Verdict:** Reproduced; strong candidate for a validated bug.

### 5. Manual node ports outside TCP range

- **Command:** `PYTHONPATH=. python - <<'PY' ...` invoking `NodesConnectionsPage._add_manual_host` with fake variables.
- **Input:** Name `n`, host `host`, port text `-1`.
- **Output:** `manual port: [('n', 'host', -1)]`.
- **Interpretation:** The UI validates only integer syntax, and the callback receives `-1`; the controller persists it without range validation. This is reachable from the manual-host form and is not a valid TCP port.
- **Verdict:** Reproduced; strong candidate for a validated bug.

### 6. Thermal thresholds outside visible graph

- **Command:** `PYTHONPATH=. python docs/bug_hunts/poc/BUG-20260909-001/thermal_threshold_poc.py`.
- **Input:** First series `(40.0, 45.0)` with warning `90.0` and critical `95.0`, graph `200x100`.
- **Output:** `(40.0, 45.0) -558.0 -622.0 18.0 82.0`, followed by an assertion failure that warning Y is outside `[top, bottom]`.
- **Interpretation:** Threshold coordinates use the sample range directly and are not clamped to the plot bounds. The second high-temperature case was not reached because the first case already failed.
- **Verdict:** Reproduced; strong candidate for a validated bug.

### 7. TypeError-text fallback repeats a partially executed operation

- **Command:** `PYTHONPATH=. python docs/bug_hunts/poc/BUG-20260909-001/agent1_counter_test.py` after the hygiene gate.
- **Input:** Synthetic primary hook appends `primary` then raises `TypeError("unexpected keyword argument 'cancel_event'")`; fallback appends `fallback`.
- **Output:** `legacy fallback calls: PASS ['primary', 'fallback']`.
- **Interpretation:** The adapter cannot distinguish an unsupported call signature from a matching TypeError raised after a side effect. The synthetic hook proves repeatability of the operation, but does not establish that a shipped production hook performs an irreversible side effect before raising this exact text.
- **Verdict:** Still plausible; conditional reproduction, not fully validated from this local evidence.

### 8. PID reuse and cleanup filesystem races

- **Command:** `PYTHONPATH=. python docs/bug_hunts/poc/BUG-20260909-001/agent1_counter_test.py` after the hygiene gate.
- **Input:** Synthetic process PID 77 reports create time `2.0`, while the expected scanned create time is `1.0`.
- **Output:** `process create-time mismatch: PASS ('PID 77 changed since it was scanned.',)`.
- **Interpretation:** The normal PID-reuse check rejects the replacement before termination. File cleanup similarly validates symlink, resolved location, and regular-file status immediately before `send2trash`; no destructive race was reproduced. A TOCTOU window remains between validation and the trash call, and real PID/filesystem races need platform-specific execution.
- **Verdict:** Original claim not reproduced; residual race remains plausible, so not disproven as a broader concurrency claim.

### 9. PowerShell online reinstall preserves stale same-version files

- **Command:** `python - <<'PY' ...` checking `install/install-online.ps1`, `install/install-online.sh`, and `install/upgrade.ps1` for force-reinstall and cleanup controls.
- **Input:** Installer source text and same-version reinstall path.
- **Output:** `install/install-online.sh force-reinstall= True remove-before= True`; `install/install-online.ps1 force-reinstall= False remove-before= False`; `install/upgrade.ps1 force-reinstall= True remove-before= True`.
- **Interpretation:** The PowerShell online installer invokes `pip install --user --break-system-packages $wheelPath` without `--force-reinstall` and without removing the existing distribution. Pip may treat an installed same-version package as satisfied, leaving stale files. Windows execution was unavailable, but the source-level omission is direct and reproducible.
- **Verdict:** Reproduced at the installer control level; strong candidate for a validated bug.

### 10. Dashboard cards or node controls lack keyboard/narrow-width accessibility

- **Command:** `python -m unittest tests.test_live_tk_resize tests.test_nodes_connections_page tests.test_dashboard_ui tests.test_ui_primitives -v`.
- **Input:** Headless widget recording tests plus live Tk resize tests where a display was available.
- **Output:** Live resize: `Ran 8 tests ... OK`; the focused headless UI suites also passed. The live tests exercised narrow and maximized page/card layouts.
- **Interpretation:** No narrow-width clipping or basic reachability failure reproduced. The existing evidence does not constitute a complete keyboard traversal/accessibility audit, especially for every dynamically rebuilt control.
- **Verdict:** Disproven for the tested narrow-width/layout claim; keyboard/accessibility completeness remains plausible and needs dedicated platform/accessibility tooling.

## Scope Expansion

The scope was expanded beyond the two candidate PoCs to injected discovery
events, a 20,000-iteration two-thread discovery stress run, forced persistence
failure, invalid manual ports, PID create-time mismatch, legacy callback side
effects, installer source comparison, and display-backed Tk resize tests. No
live LAN, Windows PowerShell, PID-reuse, or filesystem-race environment was
available.

## Repo Evidence Checked

- `maintenance/persistence.py`: UTF-8 read exception handling.
- `maintenance/preferences.py` and `maintenance/cluster.py`: documented fallback contracts.
- `maintenance/components/network_discovery.py`: callback/expiry map ownership and TTL behavior.
- `maintenance/components/scan_support.py`: TypeError-text legacy fallback.
- `maintenance/actions.py`: PID create-time, user, protected-process, path, symlink, and regular-file checks.
- `maintenance/ui/nodes_connections.py` and `window.py`: manual port parsing, permissions, and color rollback.
- `maintenance/ui/thermal_graph.py`: threshold geometry.
- `install/install-online.ps1`, `install/install-online.sh`, `install/upgrade.ps1`: reinstall behavior.
- Relevant existing network, cluster, preferences, process, UI, window, packaging, and live-resize tests.

## Commands Run

- Candidate PoCs: invalid-store encoding and thermal threshold PoCs.
- Counter-test hygiene: Ruff check/format, Pyright, and Mypy.
- Independent counter-test: `agent1_counter_test.py`.
- Focused repository tests: network discovery, cluster, preferences, process protection, thermal graph, nodes page, packaging, window, window-node, dashboard UI, UI primitives, and live Tk resize suites.
- Source-level installer comparison and injected direct controller probes.

## External Research Used

None. This reproduction role relied on repository code, candidate PoCs, and
local deterministic/injected tests; no live external calls were made.

## Counter-Test Results

- **Saved at:** `docs/bug_hunts/poc/BUG-20260909-001/agent1_counter_test.py`
- **First run:** Initial run exposed two harness defects: imports without `PYTHONPATH=.` selected the installed package, and the fake process lacked `parents()`. These were test-harness corrections, not app changes.
- **Iteration:** Corrected execution to `PYTHONPATH=.`, added the required fake backend/process seams, then reran hygiene.
- **Second run:** Hygiene passed and the counter-test output was: `discovery expiry: PASS`; `legacy fallback calls: PASS ['primary', 'fallback']`; `process create-time mismatch: PASS (...)`; `permission selection shape: PASS ['process_termination']`; `invalid UTF-8 preference load: REPRODUCED`.
- **Test proves/disproves:** Discovery expiry and PID reuse protection work on deterministic inputs. The legacy adapter can repeat a side-effecting hook under the matching TypeError condition. Invalid UTF-8 fallback failure reproduces. The permission-shape probe supported the direct controller reproduction but did not itself model the UI closure.

## Challenge

The broad candidate is not one uniformly proven defect. Five hypotheses
(2, 3, 4, 5, and 6) reproduced directly through reachable paths or candidate
PoCs. Hypothesis 9 has a direct PowerShell source-level control omission and a
credible same-version pip failure mode. Hypotheses 1, 7, and 8 remain
plausible under untested concurrency/extension/platform preconditions rather
than being disproven. Hypothesis 10's tested narrow-width claim did not
reproduce, but complete keyboard accessibility remains unmeasured.

## Verdict

**Strong, but split by hypothesis:** 2, 3, 4, 5, 6, and 9 are reproduced and
should remain under validation as independent defects. 1, 7, and 8 are still
plausible but need platform or adversarial timing evidence. 10 is disproven for
the tested layout/reachability behavior and remains only a weaker accessibility
coverage concern. The candidate should not be marked wholly disproven or wholly
validated as a single bug without per-hypothesis decisions.

### Opposing Agent 2 - Repo-Truth Skeptic

**Review scope and method:** Independent review of all ten candidate hypotheses against current implementations, callers, persistence/wire contracts, startup paths, documentation, and existing tests. No other opposition section was consulted. No app code or normal tests were changed. Candidate PoCs were run where relevant.

**1. Zeroconf transport callbacks mutate peer maps concurrently with expiry — Validated concern (P1/P2 boundary).**

- `ZeroconfDiscoveryBackend` invokes the injected listener from `ServiceBrowser` callbacks at `maintenance/components/network_discovery.py:171-174`, and `NetworkDiscovery._handle_transport_event` directly mutates `_peers` and `_service_nodes` at `maintenance/components/network_discovery.py:327-377`.
- `NetworkDiscovery.expire_stale` iterates `_peers` and deletes through `_drop_peer` at `maintenance/components/network_discovery.py:384-399`; the method has no lock or UI-thread assertion.
- `AppCoordinator.discovery_tick` calls `discovery.expire_stale()` from the application timer at `maintenance/components/coordinator.py:715-725`, while the transport callback is bridged only later by `AppCoordinator.start_discovery` at `maintenance/components/coordinator.py:678-694`.
- Thus the coordinator protects registry/UI delivery, but not the discovery component's own maps. A transport callback racing expiry can produce inconsistent peer state or `RuntimeError: dictionary changed size during iteration`. This is reachable with the real Zeroconf backend; the existing deterministic tests only serialize calls (`tests/test_network_discovery.py:491-509`).

**2. Node permission toggles replace unrelated permissions — Validated bug (P1).**

- The page exposes only three process permission controls at `maintenance/ui/nodes_connections.py:402-428` and constructs the callback payload from only those controls at `maintenance/ui/nodes_connections.py:419-426`.
- The controller assigns that payload as the complete descriptor permission set at `window.py:1224-1229` and as the complete persisted record permission set at `window.py:1230-1235`.
- Read permissions include dashboard, component, process review, and storage review at `maintenance/nodes.py:116-123`; they are not represented in the page's three-control subset. Toggling a process permission therefore silently removes unrelated read permissions, changing the remote authorization contract on the next save/reload (`maintenance/cluster.py:629-631`).
- This is not disproven by the page test: `tests/test_nodes_connections_page.py:210-216` covers color only, and the model test does not exercise the controller merge path.

**3. Node-colour persistence failure rolls back to `None`, not the old colour — Validated bug (P2).**

- `_set_node_color` mutates the registry before saving at `window.py:1249-1255`.
- On save failure it unconditionally executes `registry.set_color(..., None)` at `window.py:1268-1271`, rather than restoring the prior descriptor color. `ClusterStore.save` failures are converted to `False` by `_save_cluster_state` at `window.py:1043-1049`.
- A previously persisted non-`None` color is therefore lost in runtime state after a failed update, even though the durable old record remains unchanged. The analogous rename path restores its prior value on save failure at `window.py:1204-1206`, which establishes the intended rollback pattern and makes the color path an actual inconsistency.

**4. Invalid UTF-8 store files escape the documented startup fallback — Validated bug (P1/P2).**

- The shared reader catches `FileNotFoundError` and `OSError`, but not `UnicodeDecodeError`, at `maintenance/persistence.py:18-32`; `Path.read_text(encoding="utf-8")` at line 27 raises `UnicodeDecodeError` for invalid bytes.
- Both startup stores rely on this helper: `PreferencesStore.load` at `maintenance/preferences.py:205-213` and `ClusterStore.load` at `maintenance/cluster.py:446-458`.
- Their documented contracts explicitly say malformed/unreadable files fall back and never block startup (`maintenance/preferences.py:194-200`, `maintenance/cluster.py:435-441`). The candidate PoC `docs/bug_hunts/poc/BUG-20260909-001/invalid_store_encoding_poc.py` reproduced `UnicodeDecodeError` for both stores and exited nonzero.

**5. Manual node ports accept values outside the valid TCP range — Validated bug (P2, potentially P1 for user-facing connectivity).**

- The presentation parser accepts any integer, including negative and values greater than 65535, at `maintenance/ui/nodes_connections.py:536-550`.
- The controller stores the value without validation in the trusted record at `window.py:1348-1355`, and `ClusterStore._parse_record` validates only that the value is an `int` at `maintenance/cluster.py:545-548` (also allowing booleans as Python `int`).
- The value reaches `SocketRemoteTransport`, whose constructor stores it without range checking at `maintenance/remote.py:600-606`, and is passed to `socket.create_connection` at `maintenance/remote.py:613-615`. Existing tests intentionally use port `9` (`tests/test_nodes_connections_page.py:218-227`) and valid `5000` (`tests/test_window_nodes.py:499-503`), so they do not establish the boundary contract. This is a reachable invalid-input acceptance path, although connection failure prevents a destructive action.

**6. Thermal thresholds can be plotted outside the visible graph — Validated bug (P2).**

- The graph dynamically scales `lowest` and `highest` from sample values at `maintenance/ui/thermal_graph.py:55-60`, then maps thresholds with the same unclamped `y_for` function at `maintenance/ui/thermal_graph.py:63-76`.
- Threshold lines are drawn directly at those coordinates at `maintenance/ui/thermal_graph.py:194-210`; no clipping or range expansion exists.
- The candidate PoC `docs/bug_hunts/poc/BUG-20260909-001/thermal_threshold_poc.py` reproduced warning/critical coordinates above the canvas for samples `(40.0, 45.0)`. The existing test only asserts a threshold exists (`tests/test_telemetry_graph.py:141-148`), not that it is visible.

**7. TypeError-text legacy fallback can repeat a partially executed operation — Needs more evidence / conditional hardening opportunity (P2, not a confirmed current-path bug).**

- The shared adapter retries `fallback()` after any `TypeError` whose text contains the configured substring at `maintenance/components/scan_support.py:80-89`; it cannot distinguish Python's argument-binding failure from a TypeError raised after the primary hook performed work.
- Current production facade methods accept the modern optional arguments (`algo.py:44-53`, `algo.py:65-74`, `algo.py:87-105`), and current dialog/window callers use the adapter only to preserve older injected/monkeypatched seams (`maintenance/dialogs.py:881-890`, `maintenance/dialogs.py:1319-1329`, `window.py:2193-2200`). The normal old-signature case fails during argument binding, before user work.
- The candidate/Agent 1 probe demonstrates two calls for a deliberately constructed primary, but that is the generic helper's known behavior, not proof that an existing app hook partially executes and then raises matching text. Treat as a design risk requiring a focused real-hook PoC, not as a validated bug.

**8. Process PID reuse and cleanup filesystem races may undermine destructive-action safety — Validated residual TOCTOU concern (P1).**

- Process actions compare the supplied create time during lookup at `maintenance/actions.py:145-153`, then later invoke `terminate`/`kill` on the retained process object at `maintenance/actions.py:102-111`; there is no final identity check immediately before the action. The existing test proves only the lookup mismatch case (`tests/test_process_protection.py:71-89`). A process can change between validation and action.
- File cleanup resolves and checks the path at `maintenance/actions.py:253-265`, then calls `send2trash_fn` later at `maintenance/actions.py:267-272`; there is no directory/file identity check or atomic claim across that gap. A replacement or symlink race can change what is moved after validation.
- The code correctly rejects ordinary protected/foreign PIDs, symlinks, non-files, and out-of-Downloads paths, so this is a residual race, not evidence that the basic safety policy is absent. The candidate wording is therefore validated as a race concern but should not be inflated beyond the demonstrated TOCTOU window.

**9. PowerShell online reinstall may preserve stale same-version files — Validated bug (P1/P2 packaging).**

- `install/install-online.ps1` builds pip arguments as `install`, optional `--user`, `--break-system-packages`, and the wheel at lines `47-50`; it does not include `--force-reinstall` or `--upgrade`.
- The Windows local installer does include `--force-reinstall` at `install/install.ps1:12`, and the shared Windows helper does so at `install/_common.ps1:203-217`.
- Repository documentation explicitly requires force reinstall for exact-wheel installation at `docs/IMPLEMENTATION_PLAN_2026-09-07.md:568-581`, and the README/installed metadata describe same-version online reinstall as supported. Consequently the PowerShell online path can leave an already-installed same-version distribution in place rather than replacing its files, while verification at `install/install-online.ps1:53-67` checks version/path but not file contents.

**10. Dashboard cards or node controls may lack keyboard/narrow-width accessibility — Partly disproven, partly validated downgrade (P2).**

- Keyboard activation is present for registered buttons: `ButtonCoordinator.bind` replaces the widget command with a dispatch callback at `maintenance/ui/action_coordinator.py:56-81`, and node action buttons are registered/bound at `maintenance/ui/nodes_connections.py:383-401`; native `Button`, `Checkbutton`, `Combobox`, and `Entry` widgets remain focusable. The shared page tests cover back-button focus (`tests/test_preferences_page.py:313-319`) and narrow page reachability is covered for settings/preferences at `tests/test_live_tk_resize.py:296-329`.
- However, the manual-host form lays out three fixed-width entry holders and the add button horizontally with `side="left"` at `maintenance/ui/nodes_connections.py:445-459`, while each entry is width 16 at `maintenance/ui/nodes_connections.py:469-491`. There is no responsive wrapping or horizontal scrolling for this form. The page's scrollable canvas only provides vertical scrolling (`maintenance/ui/layout.py:125-199`).
- Verdict: no repo proof that the controls are keyboard-inaccessible, but the narrow-width claim is a real, narrower layout concern for the Nodes page. Existing narrow live-Tk coverage reaches Preferences, not Nodes (`tests/test_live_tk_resize.py:296-329`).

**Overall Agent 2 verdict:** Hypotheses 2, 3, 4, 5, 6, and 9 are confirmed repository contract/behavior bugs. Hypotheses 1 and 8 are confirmed residual concurrency/TOCTOU safety concerns with severity dependent on race reachability. Hypothesis 7 remains unconfirmed without a real current hook that partially executes before the matching `TypeError`. Hypothesis 10 is downgraded to the manual-host narrow-layout issue; its keyboard portion is not supported by current repo evidence.

**Validation record:** Ran `python docs/bug_hunts/poc/BUG-20260909-001/invalid_store_encoding_poc.py` (reproduced both decode failures), `python docs/bug_hunts/poc/BUG-20260909-001/thermal_threshold_poc.py` (reproduced out-of-bounds coordinates), and `python docs/bug_hunts/poc/BUG-20260909-001/agent1_counter_test.py` (did not complete; its fake backend emits before the component becomes active). No app code or normal tests were edited.

<!-- Reviewer-owned section. -->

### Opposing Agent 3 - Architecture/Security Skeptic

Independent architecture/security opposition. I traced the candidate paths from
UI or transport entry points through the registry/coordinator and into the
destructive or persistent boundary. I did not treat existing unit coverage as
proof against the untested interleavings or malformed inputs.

| Hypothesis | Verdict and realistic impact |
| --- | --- |
| 1. Zeroconf callbacks race expiry | **Validated reliability defect, P2.** `ZeroconfDiscoveryBackend` invokes `NetworkDiscovery._handle_transport_event` from the transport callback, where `_peers` and `_service_nodes` are mutated (`maintenance/components/network_discovery.py:327-377`). `AppCoordinator.discovery_tick()` calls `expire_stale()` from the application timer (`maintenance/components/coordinator.py:715-725`), and the event bridge only moves the later registry/UI callback onto Tk; it does not serialize the discovery component's own maps. Concurrent dictionary mutation can lose updates or raise during iteration. This is not a trust bypass: discovery records are explicitly untrusted and non-selectable, and no remote action is performed from this path. |
| 2. Permission toggles replace unrelated permissions | **Validated functional/fail-closed defect, P2.** The page emits only the three process permissions (`maintenance/ui/nodes_connections.py:402-427`), and `_set_node_permissions` replaces the complete descriptor and persisted record permission sets (`window.py:1214-1246`). Toggling one process checkbox therefore removes dashboard/component/storage/read or other permissions that were not represented by the page. The consequence is loss of authorized functionality, not privilege escalation: `RemoteService` still checks capability and permission below the UI (`maintenance/remote.py:489-498`). |
| 3. Colour persistence rollback loses the old colour | **Validated runtime-state rollback defect, P2.** `_set_node_color` mutates the descriptor, then on save failure restores `None` unconditionally (`window.py:1249-1271`). For a node previously coloured, the durable file remains unchanged while the live registry loses the old colour, producing a stale/inconsistent UI until reload. This is not a security issue and does not alter trust or authorization. |
| 4. Invalid UTF-8 store files escape fallback | **Validated startup-availability defect, P1/P2 boundary; not a confidentiality/integrity issue.** `read_text_or_none` catches `FileNotFoundError` and `OSError` but not `UnicodeDecodeError` (`maintenance/persistence.py:18-32`), while both stores document and rely on that helper for “always returns valid state” startup behavior (`maintenance/preferences.py:194-213`, `maintenance/cluster.py:435-465`). The candidate PoC reproduced `UnicodeDecodeError` for both stores. A same-user or local filesystem corruption can prevent startup, but the input is local configuration and does not grant an attacker an authenticated remote operation. I assess this as P1 only if startup availability is a release-level requirement; otherwise P2 reliability. |
| 5. Manual node ports accept values outside TCP range | **Validated input-validation defect, P2.** The page parses any integer (`maintenance/ui/nodes_connections.py:536-550`), `_add_manual_host` stores it without range checking (`window.py:1311-1356`), and the isolated probe accepted port `70000`. The value later reaches `socket.create_connection` (`window.py:1444-1458`, `maintenance/remote.py:603-626`), where platform-specific overflow/error behavior is surfaced as a connection failure. The user intentionally supplies the endpoint, so this is not SSRF or an authorization bypass; it is malformed persisted configuration and avoidable runtime failure. |
| 6. Thermal thresholds plot outside the graph | **Validated presentation defect, P2.** `threshold_y` directly applies the sample-derived scale without clamping (`maintenance/ui/thermal_graph.py:55-85`). The candidate PoC reproduced warning/critical coordinates `-558` and `-622` for ordinary 40/45 C samples, outside top/bottom. This cannot affect telemetry, actions, or trust; it is a UI correctness issue. |
| 7. TypeError legacy fallback repeats partial work | **Validated compatibility-boundary hazard, downgraded P2.** `call_legacy_compatible` retries the fallback after any matching `TypeError` (`maintenance/components/scan_support.py:63-90`). An isolated counter-test produced `['partial', 'fallback']` when the primary performed a side effect before raising matching text. Current production uses are scanner/extension compatibility paths, and no destructive action is reached through this helper in the traced app flow, so I found no security exploit or confirmed data-loss path. The helper nevertheless permits duplicate side effects for a malformed/partially executed hook and should remain a reliability finding rather than being dismissed as harmless exception handling. |
| 8. PID reuse and filesystem races undermine cleanup safety | **PID reuse disproven for the current dialog path; filesystem race remains a narrow integrity/reliability hazard, not arbitrary deletion proof.** The process dialog carries scanned `create_time` values into `ProcessManager`, which reopens the PID and compares creation time before acting (`maintenance/dialogs.py:1052-1080`, `maintenance/actions.py:127-163`); foreign users, protected names/PIDs, and unreadable descendants fail closed. Remote process actions additionally require authenticated capability and permission (`maintenance/remote.py:517-535`). For files, `FileManager` rejects symlinks, resolves strictly under Downloads, and only calls `send2trash` (`maintenance/actions.py:240-274`). There is still a check/use window between `resolve(strict=True)` and `send2trash`; a same-user concurrent actor can replace the checked in-root file and cause a different in-root file to be trashed. The resolved absolute path and symlink rejection do not demonstrate traversal to an outside target, so severity is P2 integrity/reliability, not P1 arbitrary-file deletion. |
| 9. PowerShell online reinstall preserves stale same-version files | **Disproven for the claimed stale-package path.** The online PowerShell installer installs a downloaded wheel after SHA-256 verification (`install/install-online.ps1:9-16,47-51`); the local upgrade path removes the installed distribution and then uses `--force-reinstall` (`install/upgrade.ps1:15-18`). Python package uninstall uses the distribution record to remove files it owns, and the subsequent force reinstall replaces the wheel's files. No repository evidence shows same-version package files becoming stale through these scripts. Residual untracked files would be a packaging hygiene concern, not proof of runtime code execution or privilege impact. |
| 10. Dashboard/node controls lack keyboard or narrow-width accessibility | **Needs more evidence; no security defect established.** The node page supplies ordinary Tk/ttk buttons, checkbuttons, entries, and comboboxes, with stable button registrations and focusable controls (`maintenance/ui/nodes_connections.py:197-209,346-428,453-491`). The manual-host row is horizontally composed and may be visually constrained at narrow widths, but the current headless tests do not establish clipping, focus order, or an inaccessible keyboard path. This remains a UI/accessibility investigation, not a trust-boundary issue. |

Threat-boundary conclusion: network discovery is observation-only; pairing requires
explicit user confirmation of the advertised fingerprint, and discovered peers
remain untrusted. Remote management is HMAC-authenticated, freshness/replay
checked, target-bound, and permission-checked. The confirmed concerns are thus
mostly reliability, availability, or fail-closed authorization loss. The only
destructive-action residual is the local file check/use race; current evidence
does not support arbitrary outside-root deletion or remote unauthorised cleanup.

Focused evidence run:

- `python docs/bug_hunts/poc/BUG-20260909-001/invalid_store_encoding_poc.py` failed as expected for the candidate: both stores escaped `UnicodeDecodeError`.
- `python docs/bug_hunts/poc/BUG-20260909-001/thermal_threshold_poc.py` failed as expected: threshold coordinates were outside the plot.
- `python -m unittest tests.test_network_discovery tests.test_coordinator_discovery tests.test_process_protection tests.test_storage_conservative tests.test_preferences tests.test_cluster tests.test_remote_contract -v` passed, 154 tests.
- `python -m unittest tests.test_nodes_connections_page tests.test_window_nodes tests.test_maintenance -v` passed, 125 tests.
- Inline counter-probes accepted port `70000` and demonstrated primary-side-effect plus legacy fallback execution.

No live LAN, Windows PowerShell, PID-reuse, or filesystem-race execution was
performed. Those environment-specific gaps are not treated as passes. No app
code or normal tests were modified.

### Opposing Agent 4 - External-Research Skeptic

**Review scope and method:** Independent review of all ten hypotheses using the
current repository, Python 3.12.3, installed `zeroconf` 0.151.3, and pip 24.0.
No application code or normal tests were changed. The only new artifact is the
reviewer-owned probe at
`docs/bug_hunts/poc/BUG-20260909-001/agent4_counter_test.py`. Other reviewer
sections were not used as evidence for these conclusions.

**Official sources used:**

- Python `pathlib.Path.read_text`: <https://docs.python.org/3/library/pathlib.html#pathlib.Path.read_text>
- Python built-in exception hierarchy, including `UnicodeDecodeError` and
  `OSError`: <https://docs.python.org/3/library/exceptions.html>
- Python Tkinter threading model: <https://docs.python.org/3/library/tkinter.html#threading-model>
- Python socket address semantics and errors:
  <https://docs.python.org/3/library/socket.html>
- Python subprocess behavior and Windows process semantics:
  <https://docs.python.org/3/library/subprocess.html>
- python-zeroconf API reference, including threaded `ServiceBrowser` and
  `Zeroconf` lifecycle: <https://python-zeroconf.readthedocs.io/en/latest/api.html>
- pip `install` options and `--force-reinstall`:
  <https://pip.pypa.io/en/stable/cli/pip_install/>

**Focused evidence runs:**

- `python docs/bug_hunts/poc/BUG-20260909-001/invalid_store_encoding_poc.py`
  failed as designed: both stores printed escaped `UnicodeDecodeError` and the
  process exited nonzero.
- `python docs/bug_hunts/poc/BUG-20260909-001/thermal_threshold_poc.py`
  failed as designed on the low-valued sample: threshold coordinates were
  `-558.0` and `-622.0`, outside the plot bounds `18.0..82.0`.
- `python docs/bug_hunts/poc/BUG-20260909-001/agent4_counter_test.py` was run
  twice. Both runs reported `invalid_utf8_escaped: ['PreferencesStore',
  'ClusterStore']`, `thermal_thresholds_outside: True`, and
  `legacy_calls: 1 1`.
- `ruff check` and `ruff format --check` on the reviewer probe passed;
  `python -m unittest tests.test_nodes_connections_page -v` passed all 17
  existing focused tests.

**Per-hypothesis assessment:**

1. **Zeroconf callbacks race expiry — Strong.** The installed version satisfies
   the project requirement `zeroconf>=0.131` (`pyproject.toml:16`) and its
   official API documents `ServiceBrowser` as a threaded browser that fires
   listener callbacks. The backend forwards those callbacks directly at
   `maintenance/components/network_discovery.py:171-174`; the callback mutates
   `_peers`/`_service_nodes` at lines 327-377 while `expire_stale` iterates and
   deletes at lines 384-399. Python threading documentation confirms shared
   memory between threads, but does not make compound dictionary iteration and
   mutation a safe operation. The claim is therefore compatible with the
   documented runtime model and remains a strong concern. No live LAN test was
   run.

2. **Permission toggles replace unrelated permissions — Strong.** This is
   repo behavior rather than a library-semantics dispute. The controller turns
   the UI subset into the complete permission set at `window.py:1224-1235`,
   while `READ_PERMISSIONS` includes dashboard, component, process-review, and
   storage-review permissions at `maintenance/nodes.py:116-123`. Nothing in
   Python/Tk or the official remote semantics rescues omitted values. Verdict:
   strong support for the concern.

3. **Colour rollback loses the old colour — Strong.** The rollback assignment
   is literally `None` at `window.py:1268-1271`; no external semantic ambiguity
   exists. The relevant Tk documentation only establishes that widget colour
   values are ordinary configuration values, not persistence rollback rules.
   The concern is strongly supported for any existing non-`None` colour.

4. **Invalid UTF-8 escapes startup fallback — Strong.** `Path.read_text` is
   documented to decode file contents using the supplied encoding. Python’s
   exception hierarchy documents `UnicodeDecodeError` as a `UnicodeError`, and
   `UnicodeError` as a `ValueError`, not an `OSError`. Therefore the helper’s
   `except OSError` at `maintenance/persistence.py:29-32` cannot catch this
   decode failure. The current Python 3.12 probe reproduced it for both stores.
   `Path.read_text` has supported this API since Python 3.5, so the result
   applies to the project’s `requires-python >=3.10` range.

5. **Manual ports accept values outside the TCP range — Strong.** The UI calls
   `int()` without a range check at `maintenance/ui/nodes_connections.py:536-550`,
   and the controller persists it at `window.py:1348-1355`. Python’s socket
   documentation describes an IPv4 socket address as `(host, port)` with an
   integer port and says address-semantic failures raise `OSError`; it does not
   convert arbitrary integers into valid ports. The repository never validates
   0..65535 before persistence. The exact connection failure is platform/socket
   dependent, but acceptance of invalid input is strongly supported.

6. **Thermal thresholds plot outside the graph — Strong.** The pure geometry
   function maps thresholds with `y_for` and does not clamp them at
   `maintenance/ui/thermal_graph.py:63-85`. The candidate and reviewer probes
   reproduce coordinates outside the visible bounds. No Tk-version behavior is
   involved in the geometry calculation; the conclusion applies across the
   project’s supported Python versions.

7. **TypeError-text fallback can repeat a partial operation — Still plausible.**
   Python documents `TypeError` as applicable to inappropriate operations and
   explicitly allows user code to raise it; the exception message is not a
   reliable proof that no side effect occurred. The helper catches a matching
   message at `maintenance/components/scan_support.py:80-89` and then calls the
   fallback. The reviewer probe demonstrates the control flow after a primary
   side effect (`primary` count 1, fallback count 1), but not a real extension
   hook whose partial operation is later repeated. This is a credible narrow
   hazard, not independently a confirmed production bug.

8. **PID reuse/filesystem races undermine destructive-action safety — Still
   plausible, not confirmed by external semantics.** The code does compare
   process creation times at `maintenance/actions.py:145-153`, and Python’s
   subprocess/process documentation does not provide an atomic identity-plus-
   action guarantee for this psutil-style sequence. `FileManager` similarly
   checks then calls `send2trash` at lines 249-268. However, official Python
   documentation alone cannot establish the timing window’s exploitability or
   psutil’s platform-specific identity guarantees, and no process/filesystem
   race PoC was run. Keep as plausible pending an OS-specific test.

9. **PowerShell online reinstall may preserve stale same-version files — Strong.**
   `install/install-online.ps1:47-50` invokes pip install without
   `--force-reinstall` or `--upgrade`. Current official pip documentation says
   `pip install` prefers to leave the installed version as-is unless upgrade is
   specified, and defines `--force-reinstall` as reinstalling packages even when
   up to date. This behavior is directly applicable to the script’s local wheel
   and same-version scenario. Windows execution was unavailable here, so the
   script was not run, but the command-line defect is directly evidenced.

10. **Dashboard/node controls lack keyboard or narrow-width accessibility —
    Weak.** Python/Tk documentation confirms keyboard focus and event bindings
    exist, and the repository uses real `ttk.Button` controls plus a scrollable
    layout. It does not provide a general accessibility conformance guarantee,
    nor does a headless widget test establish rendered narrow-width behavior.
    The manual-host form’s horizontal packing at
    `maintenance/ui/nodes_connections.py:445-491` is a lead for a visual test,
    not enough external or empirical evidence to validate the broad hypothesis.

**Verdict:** Strong support for hypotheses 1-6 and 9; hypothesis 2, 3, 4, 5,
and 6 are especially directly established by repo code plus focused evidence.
Hypotheses 7 and 8 remain plausible but need a production-shaped counterexample
or platform-specific race test. Hypothesis 10 is weak pending display-backed
keyboard and narrow-width evidence. No external source was used to override
repo behavior; official documentation was used only for the library/runtime
semantics stated above.

## Agent 5 - Superpower Evidence Auditor

### Inputs read
- Candidate entry: `docs/bug_hunts/bugs_found.md`.
- Opposition file: this complete artifact, including all four opposition sections,
  candidate PoCs, counter-test paths, baseline gates, and environment limits.
- Prior patch reviews: `PATCH-20260909-001`, `002`, `003`, `005`, `006`, `007`,
  `008`, plus the directly relevant `PATCH-20260908-004` permission/remote review.
  No `PATCH-20260909-004` file exists.
- Rejected hypotheses: no `docs/bug_hunts/rejected/` volume or matching rejected
  artifact exists in this checkout.
- Repo docs: `AGENTS.md`, `docs/window-extraction-plan.md`, and the active
  persistence, remote, component, packaging, and UI ownership documentation.
- Exact files: `window.py`, `algo.py`, `maintenance/actions.py`, `cluster.py`,
  `persistence.py`, `preferences.py`, `nodes.py`, `remote.py`, all current
  `maintenance/components/` and `maintenance/ui/` modules, all relevant tests,
  and `install/install-online.ps1`, `install/install-online.sh`, `install.ps1`,
  and `upgrade.ps1`.
- LR commands/list: the recorded `./lr --list`, `./lr impact`, `./lr 7`, and
  `./lr secrets` attempts are unavailable because no `./lr` executable exists.

### Additional repo probes
| Probe | Result | Why it matters |
|---|---|---|
| Full unittest discovery | 978 passed in 44.097s | Covered current lifecycle, node, remote, UI, persistence, packaging, and safety paths. |
| Ruff and format | `ruff check .` passed; 266 files formatted | Reviewer PoC and repository hygiene are eligible evidence. |
| Pyright/Mypy | 0 Pyright diagnostics; Mypy success for 118 source files | No current static gate contradiction. |
| Compile/diff checks | `py_compile` and `git diff --check` passed | Current Python syntax and patch whitespace are clean. |
| Agent 5 counter-test | Passed twice; all six probe groups produced expected observations | Independent evidence for all ten hypotheses where safe, without app-code/test edits. |
| Pip same-version dry run | `pip install --dry-run --no-deps dist/system_analyzer-1.3.7.1-py3-none-any.whl` reported already installed and instructed `--force-reinstall` | Resolves the H9 disagreement at the installed pip 24.0 semantics boundary. |

### Additional LR/drift evidence
| Command | Result | Interpretation |
|---|---|---|
| `./lr --list` | unavailable: executable absent | LR inventory is not verified. |
| `./lr impact`, `./lr 7`, `./lr secrets` | unavailable per baseline artifact; no executable exists | These are unavailable gates, never passes. No drift/secrets conclusion is claimed. |

### Prior bug-hunt pattern match
- Similar prior bug: `PATCH-20260908-004` identified permission migration/defaulting
  and remote target-boundary defects; its explicit permission model makes the
  current UI subset replacement in H2 a related, narrower regression.
- Similar rejected hypothesis: none found in the repository; the absent rejected
  volume is an evidence limitation, not evidence of rejection.
- Reusable lesson: passing low-level transport or focused UI tests does not prove
  composition-root lifecycle, persistence rollback, or target isolation. Compare
  the complete caller path and preserve fail-closed/rollback contracts.

### External research pack used
| Source | Type | What it proves / disproves | Primary or secondary |
|---|---|---|---|
| Python `pathlib`, exceptions, socket, Tkinter, threading documentation cited by Agents 1/4 | Official language/library docs | Decode errors are not `OSError`; socket ports/errors and threaded callback/UI semantics have the stated boundaries. | Primary |
| python-zeroconf API and tagged source cited by Agents 2/4 | Official project docs/source | `ServiceBrowser` callbacks are threaded; address/property accessor semantics support H1 and the reviewers' IPv6 distinctions. | Primary |
| pip install options and local dry-run | Official pip behavior plus local runtime evidence | Same-version local wheel is skipped absent `--force-reinstall`; supports H9. | Primary |
| Tcl/Tk and send2trash references cited in prior reviews | Official/authoritative project docs | Timer cancellation and reversible Trash behavior do not remove the identified application-level races. | Secondary for this audit |

### Validated search set performed
- official language docs: reviewed cited Python exception, pathlib, socket,
  threading, Tkinter, and subprocess semantics.
- official framework/library docs: reviewed cited Zeroconf, pip, Tcl/Tk, and
  send2trash semantics.
- official tool docs: pip CLI semantics were checked locally with `--dry-run`.
- changelog/release notes: not used; no version-change question remained after
  installed pip/Zeroconf evidence.
- issue tracker search: not performed; repo/runtime evidence was sufficient.
- Stack Overflow search: not performed; community material was unnecessary.
- sibling-bug repo search: searched all old/new component, window, action,
  persistence, remote, UI, installer, and test paths for the ten patterns.
- prior bug-hunt search: searched all available opposition and patch-review
  artifacts, including prior permission, discovery, lifecycle, storage, and
  compatibility findings.

### New sibling-bug search
- nearby files checked: `window.py`, `maintenance/nodes.py`, `cluster.py`,
  `remote.py`, `actions.py`, `persistence.py`, `network_discovery.py`,
  `scan_support.py`, `thermal_graph.py`, `nodes_connections.py`, all extracted
  component modules, all installer variants, and their tests.
- same pattern elsewhere: rename rollback restores the old value; color rollback
  does not. Other store parsers share the same UTF-8 reader. Discovery updates
  and expiry share the peer maps. Installer siblings explicitly remove or force
  reinstall. These sibling differences are contract evidence, not speculation.
- cross-language variant checked: Bash online installer removes the existing
  package and uses `--force-reinstall`; Windows local/upgrade scripts do likewise.
- prior bug-hunt/rejected-hypothesis match: permission/defaulting and remote
  target-boundary findings in `PATCH-20260809-004` remain the closest match;
  no rejected-hypothesis artifact was present.
- result: H2, H3, H4, H9 are strengthened by sibling inconsistency; H1/H8 are
  residual concurrency patterns also present at explicit check/use boundaries;
  no additional sibling defect was promoted.

### Phase 3 - Own counter-test

**Saved at:** `docs/bug_hunts/poc/BUG-20260909-001/agent5_counter_test.py`

**Initial test design:**
- Logic: exercise safe deterministic runtime seams, pure thermal geometry,
  process identity rejection, a concurrent discovery stress case, and source
  contract checks for controller/UI/persistence/installer behavior.
- Test cases: six probe groups covering H1; H2-H5/H9; H6; H7; H8; and H10.
  The source group intentionally verifies behavior without constructing a live
  Tk window or invoking an installer.

**First run:**
- Result: 6/6 probe groups completed; no errors or timeouts.
- Key findings: discovery stress did not raise; H2-H5/H9 source contracts,
  H6 out-of-bounds geometry, H7 repeatable fallback, H8 PID replacement
  rejection, and H10 fixed horizontal layout were observed.
- Timing: completed within the command timeout; no external service was used.

### Phase 4 - Test iteration

**Changes made based on re-read:**
- Corrected only the Agent 5 PoC harness: import ordering, repository-root
  calculation, callback narrowing, override parameter naming, and Ruff/Pyright/
  Mypy hygiene. No app code, normal tests, reviewer sections, or baselines were
  changed.

**Second run:**
- Result: identical 6/6 probe-group output; no errors or timeouts.
- Key findings: the concurrent stress non-failure is not a race disproval;
  source probes and pure runtime probes remain reproducible. The separate pip
  dry-run independently showed same-version installation is skipped without
  force reinstall.
- Timing: completed within the command timeout.

**Empirical verdict from test results:**
- H2, H3, H4, H5, H6, H7, H9, and H10's narrower layout observation are
  empirically supported. H8's safe PID-reuse rejection is empirically supported,
  but the destructive check/use race itself was not triggered. H1's stress run
  did not trigger an exception, so it supports neither a clean pass nor a full
  runtime reproduction. The counter-test does not prove keyboard inaccessibility.

### Phase 5 - Per-hypothesis classification

| # | Hypothesis | Classification | Confidence | Evidence and boundary |
|---|---|---|---|---|
| 1 | Zeroconf callback/expiry concurrent map mutation | **Validated downgraded bug, P2** | Medium | Official threaded callback model, unsynchronized `_peers` iteration/mutation, and reachable coordinator timer path establish a real reliability boundary. The 20,000-call stress run did not reproduce an exception; no P1 impact or corruption is proven. |
| 2 | Permission toggle replaces unrelated permissions | **Validated bug, P2** | High | Reachable page emits only process permissions; controller persists them as the complete set, dropping dashboard/component/storage permissions. This is authorization loss/fail-closed functionality, not privilege escalation. |
| 3 | Color failure rolls back to `None` | **Validated bug, P2** | High | Current code literally restores `None`; rename rollback restores the prior value. Direct forced-save-failure probe returned `None` from a prior non-`None` color. |
| 4 | Invalid UTF-8 escapes startup fallback | **Validated bug, P1** | High | `Path.read_text(encoding="utf-8")` raises `UnicodeDecodeError`, which shared helper does not catch; both stores promise malformed/unreadable startup fallback. Candidate PoC reproduced both stores. P1 reflects explicit startup-availability contract; severity may be P2 if product availability is intentionally lower. |
| 5 | Manual ports outside TCP range accepted | **Validated bug, P2** | High | UI accepts arbitrary integers and persistence/transport do not enforce 0..65535. Direct probes accepted `-1` and `70000`; later socket failure is avoidable malformed configuration. |
| 6 | Thermal thresholds outside graph | **Validated bug, P2** | High | Pure layout maps 90/95 against 40/45 samples to `-558/-622`, outside `18..82`; no Tk/environment ambiguity exists. |
| 7 | TypeError legacy fallback repeats partial operation | **Needs more evidence** | Medium | Helper retries after matching text and synthetic side-effect probe shows duplicate calls, but no shipped hook was shown to side-effect before raising that exact binding-like message. Treat as conditional hardening, not current production bug. |
| 8 | PID/filesystem races undermine destructive-action safety | **Validated downgraded bug, P2** | Medium-low | PID create-time mismatch is correctly rejected; file and process paths have a check/use gap before action. No real replacement race or outside-root deletion was reproduced, and current controls prevent the broad P1/arbitrary-deletion claim. |
| 9 | PowerShell online reinstall preserves same-version stale files | **Validated bug, P2** | High | Script omits `--force-reinstall`; local pip 24.0 dry-run says same-version wheel is already installed and explicitly requires that option. Windows execution unavailable, but command-level semantics and sibling scripts establish the omission. |
| 10 | Dashboard/node controls lack keyboard/narrow-width accessibility | **Needs more evidence** | Low | Focusable native controls and narrow layout tests disprove the broad keyboard/reachability claim. Fixed horizontal manual-host row is a credible narrower UI concern, but no display-backed Nodes render/focus audit proves user-visible clipping. |

### Agent 5 conclusion
**Decision pressure:** strengthens validation for H2-H6 and H9; narrows H1 and
H8; rejects cheap validation of H7 and H10; changes H1/H8 from the broad proposed
severity to P2 residual defects.

**Reason:** Independent probes and the full current suite agree on the direct
contract violations. Passing tests cover ordinary serialized paths and safety
controls, not malformed UTF-8, omitted permission merging, failed rollback,
invalid ports, unclamped thresholds, same-version pip behavior, or adversarial
check/use interleavings. The only direct disagreement, H9, is resolved by the
local pip dry-run. H1 and H8 remain real narrow hazards but lack a reproduced
failure under this environment. H7 and H10 lack a reachable production failure
under the claimed broad wording.

**Recommendation:** split the candidate into independent ledger decisions rather
than marking the broad audit wholly validated or wholly disproven. Validate H2,
H3, H4, H5, H6, and H9 as separate bugs; record H1 and H8 as validated
downgraded P2 residuals if the ledger permits split entries, otherwise mark the
umbrella as partially validated with explicit narrowed scope. Keep H7 and H10
as Needs more evidence. Do not implement fixes in this Mode B audit.

**What main auditor must verify next:** retain per-hypothesis status/severity,
record the six direct validated defects separately, preserve the H1/H8 evidence
limits, and do not treat missing `./lr`, absent Windows execution, absent live
LAN, absent race-triggering platform, or absent accessibility tooling as passes.

## Main Auditor Rebuttal

All four independent opposition reviews and Agent 5 were completed in the
required order. The evidence is consistent for the direct contract violations:
the UI sends a process-only permission subset which the controller persists as
the complete set; colour failure restores the wrong value; invalid UTF-8 is not
handled by the shared startup reader; manual ports are not range-validated;
thermal thresholds are mapped outside the visible plot; and the PowerShell
online installer omits the force-reinstall control used by its sibling paths.

The discovery race is a real unsynchronised shared-map boundary but did not
reproduce in the available stress run, so it is a validated downgraded P2
reliability bug, not a P1 crash claim. The destructive-action check/use window is
also retained as a downgraded P2 residual race: existing PID identity and path
guards work, while no platform-specific replacement race or outside-root
deletion was reproduced.

The TypeError-text fallback remains a conditional hazard only. Its synthetic
side-effect probe proves duplicate control flow, but no shipped hook was shown
to partially execute before raising the matching binding-like error. The broad
keyboard-accessibility claim is not supported; the narrower manual-host layout
concern needs a display-backed Nodes-page audit.

The full test and static suite passing does not contradict these findings because
the missing cases are malformed bytes, omitted permission merging, failed
rollback, invalid ports, out-of-range graph thresholds, installer same-version
semantics, and adversarial concurrency. `./lr`, Windows, live LAN, race-triggering
platforms, and complete accessibility tooling were unavailable and are recorded
as gaps rather than passes.

## Final Decision

Partially validated. Record hypotheses 2, 3, 4, 5, 6, and 9 as validated bugs;
record hypotheses 1 and 8 as validated downgraded P2 bugs; keep hypotheses 7 and
10 as Needs more evidence. Do not treat the umbrella candidate as one uniform
bug.

## Remaining Risks and Gaps

Real LAN/Zeroconf concurrency, display-backed Tk focus/layout, Windows
PowerShell execution, PID reuse, and filesystem race windows may require
platform-specific environments. Missing `./lr` is an unverified gate, not a pass.
