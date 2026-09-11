# Coordinator/Worker Roles Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Resolve the remaining review findings, clarify logical storage-cap semantics, validate the final dashboard and role lifecycle, and archive the completed implementation plan.

**Architecture:** Keep the current role, persistence, remote, storage, UI, and shared-coordinator boundaries. Treat `SnapshotBatch.encoded_size` as logical retained payload accounting; do not add a physical quota subsystem. Finish with adversarial evidence and release validation.

**Tech Stack:** Python 3.12, Tkinter/ttk, SQLite, `unittest`, wheel build scripts, BugGuard fallback reviewers.

---

## File Map

- Modify `maintenance/components/cluster_storage.py`: make logical-cap terminology explicit.
- Modify `maintenance/diagnostics.py` and `maintenance/ui/diagnostics_page.py`: expose logical storage wording.
- Modify `docs/CLUSTER_ROLES_FAILOVER_2026-09-11.md`: document the cap contract and degraded disk-full state.
- Modify `tests/test_cluster_storage.py`, `tests/test_diagnostics.py`, and `tests/test_window_nodes.py`: closure regressions.
- Create `docs/bug_hunts/patch_reviews/PATCH-20260911-002-review.md`: final BugGuard Mode A evidence.
- Move `docs/plans/2026-09-11-coordinator-worker-roles.md` to `docs/plans/archive/` after validation.

## Task 1: Lock Down Logical-Cap Semantics

**Files:** `maintenance/components/cluster_storage.py`, `tests/test_cluster_storage.py`

- [x] **Step 1: Write a failing terminology/contract test.**

```python
def test_storage_status_reports_logical_payload_budget(self) -> None:
    store = CoordinatorTimeline(self.path / "history.db", max_bytes=20)
    status = store.status()
    self.assertEqual(status.max_bytes, 20)
    self.assertEqual(store.capacity_basis, "logical encoded payload bytes")
```

- [x] **Step 2: Run the focused test and confirm the API is missing.**

Run: `python3 -m unittest tests.test_cluster_storage.ClusterStorageTests.test_storage_status_reports_logical_payload_budget -v`

Expected: `AttributeError` because `capacity_basis` does not yet exist.

- [x] **Step 3: Add the minimal read-only contract property.**

```python
    @property
    def capacity_basis(self) -> str:
        return "logical encoded payload bytes"
```

Add this property to `_BatchStore`, inherited by `CoordinatorTimeline` and `StandbyBuffer`. Do not change purge or SQLite error behavior.

- [x] **Step 4: Run storage tests.**

Run: `python3 -m unittest tests.test_cluster_storage -v`

Expected: all storage tests pass.

- [ ] **Step 5: Commit the focused change.**

```bash
git add maintenance/components/cluster_storage.py tests/test_cluster_storage.py
git commit -m "docs: clarify logical cluster storage budget"
```

## Task 2: Align Diagnostics and Operations Documentation

**Files:** `maintenance/diagnostics.py`, `maintenance/ui/diagnostics_page.py`, `docs/CLUSTER_ROLES_FAILOVER_2026-09-11.md`, `tests/test_diagnostics.py`

- [x] **Step 1: Add a failing serialized-diagnostics assertion.**

```python
def test_cluster_diagnostics_labels_logical_storage_budget(self) -> None:
    diagnostic = ClusterDiagnostic(
        "coordinator", "coord", 2, 1.0, 10, 20, 0, 256,
        "normal", 100.0, False, None,
    )
    self.assertNotIn("physical disk", serialize_cluster_diagnostic(diagnostic))
```

- [x] **Step 2: Run the focused diagnostics tests.**

Run: `python3 -m unittest tests.test_diagnostics -v`

Expected: the new test passes against the existing redacted model; the task then changes only user-facing labels and documentation.

- [x] **Step 3: Change the diagnostics label without changing the model shape.**

In `maintenance/ui/diagnostics_page.py`, change the Cluster section row from `("History", ...)` to `("History (logical bytes)", ...)`. Keep `database_bytes` and `database_cap_bytes` names for compatibility.

- [x] **Step 4: Document the exact storage contract.**

Add a subsection stating that `encoded_size` totals are logical retained payload accounting, SQLite full/I/O/locked errors pause writes, physical file/journal size is not represented by `StorageStatus.bytes_used`, and operators must use the warning plus filesystem monitoring for disk pressure.

- [x] **Step 5: Run documentation-boundary tests.**

Run: `python3 -m unittest tests.test_diagnostics tests.test_cluster_storage -v`

Expected: all tests pass and no secrets appear in serialized diagnostics.

## Task 3: Add Role and Dashboard Closure Regressions

**Files:** `tests/test_window_nodes.py`, `tests/test_cluster_roles_persistence.py`, `tests/test_dashboard_ui.py`

- [x] **Step 1: Add a role-revoke composition regression.**

Use a controller fake with one trusted context, provider, grant, and active role. Invoke `window_node_actions.revoke_node(controller, node_id)` and assert the saved role is `revoked=True`, the trusted record and grant are removed, the provider is invalidated, and registry cleanup is called.

- [x] **Step 2: Add malformed-persistence regressions.**

Write schema-v2 JSON containing `NaN` invite expiry and duplicate active Coordinator roles. Load through `ClusterStore`; assert malformed invites are skipped and duplicate role records do not create multiple active Coordinators.

- [x] **Step 3: Add the dashboard footer structure assertion.**

Use the existing recording dashboard factory and assert `target_status_label` and `refreshed_label` share `dashboard_meta_frame`, with refreshed packed left and target status packed right.

- [x] **Step 4: Run the closure regressions.**

Run: `python3 -m unittest tests.test_window_nodes tests.test_cluster_roles_persistence tests.test_dashboard_ui -v`

Expected: all tests pass.

## Task 4: Final BugGuard Evidence

**Files:** `docs/bug_hunts/patch_reviews/PATCH-20260911-002-review.md`

- [x] **Step 1: Create the Mode A review scaffold.**

Record risk `high`, full A4 threshold, changed files, tests, unavailable tools, and the logical-cap decision. Do not write reviewer-owned sections.

- [x] **Step 2: Run fallback Opposers 1-4 independently.**

Each reviewer must inspect the final diff, run its role-specific counter-tests, and write only its own section directly into the artifact. The main auditor must not read the sections until all four are complete.

- [x] **Step 3: Run fallback Agent 5.**

After all four sections exist, Agent 5 must reconcile them, run its own evidence tests, inspect related reviews, and write only `## Agent 5 evidence audit`.

- [x] **Step 4: Write the main auditor rebuttal.**

Resolve findings against exact current source and tests. Mark the physical-cap issue as a documented contract limitation, not a hidden pass. The two confirmed findings (no-role-assignment revoke dead-end; unguarded diagnostics label) were resolved in-patch with guarded regressions (`test_role_less_trusted_node_can_still_be_revoked`; `test_cluster_history_row_is_labeled_as_logical_bytes`) and the final decision is `safe`.

## Task 5: Final Validation and Archive

**Files:** `docs/plans/archive/2026-09-11-coordinator-worker-roles.md`, `dist/SHA256SUMS`, release wheel

- [x] **Step 1: Run focused validation.**

```bash
python3 -m unittest tests.test_cluster_roles tests.test_cluster_roles_persistence tests.test_cluster_storage tests.test_cluster_failover tests.test_remote_contract tests.test_peer_connection tests.test_nodes_connections_page tests.test_cluster_page tests.test_diagnostics tests.test_diagnostics_page tests.test_cluster_adversarial tests.test_dashboard_ui -v
```

Result: `Ran 157 tests ... OK` (verified across three repeat runs; one initial single flake was not reproducible).

- [x] **Step 2: Run repository validation.**

```bash
python3 -m unittest discover -s tests -q
python3 -m compileall -q maintenance tests
git diff --check
```

Expected: all tests pass; warnings from fakes or unavailable host hardware are recorded separately.

Result: full suite `Ran 1237 tests ... OK`; `compileall` and `git diff --check` exit 0.

- [x] **Step 3: Run available static and release checks.**

Run `ruff check .`, `ruff format --check .`, `pyright`, and `mypy --ignore-missing-imports`; record command-not-found failures without calling them passes. Then run `SA_VERSION_BUMP=none ./install/build.sh`, `./install/verify.sh 1.5.0.0`, and `sha256sum -c SHA256SUMS` from `dist/`.

Result: `ruff`, `ruff format`, `pyright`, `mypy`, and `./lr` are all command-not-found (recorded, not passing). `SA_VERSION_BUMP=none ./install/build.sh` rebuilt the wheel; `./install/verify.sh 1.5.0.0` reported `contents OK: 91 members; no forbidden paths` and `SHA256SUMS OK`; `sha256sum -c SHA256SUMS` from `dist/` reported `system_analyzer-1.5.0.0-py3-none-any.whl: OK`.

- [x] **Step 4: Archive the completed original plan.**

Move `docs/plans/2026-09-11-coordinator-worker-roles.md` to `docs/plans/archive/2026-09-11-coordinator-worker-roles.md`. Add a closing note in the archived plan linking to this closure plan and the final patch review.

Result: the plan was moved to `docs/plans/archive/` and its `Closure Follow-Up` note links to this closure plan and to `docs/bug_hunts/patch_reviews/PATCH-20260911-002-review.md`.

- [x] **Step 5: Review the final worktree.**

Run `git status --short`, `git diff --stat`, and `git log --oneline -10`. Confirm the new closure plan, design, archive move, code changes, tests, docs, review artifact, and wheel are the only intended changes.

Result: the worktree contains the coordinator-worker implementation (from the archived plan) plus the closure additions; the archive move, closure plan/design, both patch reviews, documentation, tests, and the rebuilt 1.5.0.0 wheel are present. No commit was created (commit steps remain pending explicit user approval).

## Self-Review Checklist

- **Coverage:** logical storage semantics, diagnostics, role revoke, malformed migration, dashboard footer, BugGuard, release validation, and archive move each have a task.
- **Boundaries:** no physical quota subsystem, new scheduler, executor, or arbitrary RPC is introduced.
- **Evidence:** unavailable static/native tools remain explicitly reported.
- **Archive:** the original plan is moved only after focused/full validation and final review.
