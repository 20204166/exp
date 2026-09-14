# Cluster Capability Visibility Amendment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add authenticated, per-subcoordinator/per-node capability grants and temporary read-only dashboard sharing without changing established local behavior or safety owners.

**Architecture:** Extend the existing role, trusted-node, remote protocol, and target-authorization owners. Default remote visibility is read-only/private; only the active Coordinator can grant selected capabilities inside its cluster. Temporary dashboard sharing remains an authenticated, bounded, non-persistent read-only session.

**Tech Stack:** Python, frozen dataclasses, typed JSON protocol, SQLite/cluster persistence, Tkinter/ttk, unittest, Ruff, Pyright, Mypy.

---

## File Structure Map

- Modify `maintenance/remote_support/protocol.py`: add typed grant/revoke/share operation names and required-capability mapping.
- Modify the existing remote request/handler modules under `maintenance/remote.py` and `maintenance/remote_support/`: validate issuer, epoch, target, grant, and share state at the target boundary.
- Modify `maintenance/nodes.py` and `maintenance/components/cluster_roles.py`: retain scoped grant/share state with existing identity and role owners.
- Modify `maintenance/cluster.py`: persist durable grant state through the existing atomic cluster store; do not persist temporary shares.
- Modify `maintenance/ui/cluster_page.py`, `maintenance/ui/nodes_connections.py`, and `maintenance/ui/window_node_actions.py`: expose semantic sharing and permission callbacks only.
- Modify `maintenance/ui/diagnostics_page.py` and `window.py`: gate developer diagnostics/export without changing internal observation.
- Add focused tests beside the existing protocol, node, role, lifecycle, UI, and diagnostics tests.
- Add no new scheduler, executor, database, generic permission framework, or transport.

### Task 1: Model Scoped Authorization State

**Files:**
- Modify: `maintenance/nodes.py`, `maintenance/components/cluster_roles.py`, `maintenance/cluster.py`
- Test: existing node/role/cluster test modules

- [ ] **Step 1: Write failing model tests** for default read-only state, grants scoped by subject and target, independent capability combinations, revocation, temporary share expiry, and non-persistence of temporary shares.
- [ ] **Step 2: Run focused tests and confirm failure.** Run `python -m unittest tests.test_nodes tests.test_cluster_roles tests.test_cluster -v`; expect missing grant/share state or authorization behavior.
- [ ] **Step 3: Add the smallest frozen grant/share records** using existing node IDs, role types, capabilities, timestamps, and epoch/fencing values. Keep temporary shares in runtime state only.
- [ ] **Step 4: Extend existing atomic cluster persistence additively** so old records load with empty grants and no shares. Reject malformed records without creating partial authorization.
- [ ] **Step 5: Run focused tests and commit** with `git add` limited to model, persistence, and tests; use commit message `feat: model scoped cluster capabilities`.

### Task 2: Enforce Protocol Authorization

**Files:**
- Modify: `maintenance/remote_support/protocol.py`, `maintenance/remote.py`, `maintenance/remote_support/`
- Test: existing remote protocol, authorization, lifecycle, and security tests

- [ ] **Step 1: Add failing request tests** proving workers cannot grant, subcoordinators cannot delegate, outside-cluster targets cannot elevate, missing capabilities are rejected, and stale/revoked grants fail closed.
- [ ] **Step 2: Run focused remote tests** with `python -m unittest discover -s tests -p 'test_remote*.py' -v`; confirm the new operations are not yet accepted.
- [ ] **Step 3: Add dedicated typed operations** for grant, revoke-grant, start-share, stop-share, and shared-dashboard read. Do not overload role assignment or arbitrary RPC dispatch.
- [ ] **Step 4: Validate every target request** against authenticated identity, cluster membership, target node, active Coordinator role, epoch/fencing token, grant subject/target/capability, and share expiry. Keep cleanup and process termination separate.
- [ ] **Step 5: Add bounded authorization-failure diagnostics** without recording credentials, tokens, or raw payloads.
- [ ] **Step 6: Run focused tests and commit** as `feat: enforce cluster capability authorization`.

### Task 3: Preserve Temporary Read-Only Sharing

**Files:**
- Modify: existing temporary-dashboard provider/request handlers and `maintenance/nodes.py`
- Test: existing remote lifecycle and temporary-dashboard tests

- [ ] **Step 1: Add failing lifecycle tests** for explicit share, read-only snapshot access, stop sharing, session expiry, disconnect invalidation, and no collection/timeline writes.
- [ ] **Step 2: Run the temporary-dashboard tests** and confirm expiry/disconnect and privacy cases fail.
- [ ] **Step 3: Reuse the existing authenticated temporary-dashboard path** with an in-memory share session keyed by owner, viewer, target, and session expiry.
- [ ] **Step 4: Ensure shared snapshots are bounded** and cannot invoke actions, collection, role changes, grants, or timeline writes.
- [ ] **Step 5: Run tests and commit** as `feat: enforce temporary dashboard sharing`.

### Task 4: Add Coordinator Permission Controls

**Files:**
- Modify: `maintenance/ui/cluster_page.py`, `maintenance/ui/nodes_connections.py`, `maintenance/ui/window_node_actions.py`, relevant `window.py` composition callbacks
- Test: existing cluster/node UI tests and new capability-control tests

- [ ] **Step 1: Add failing UI tests** for private default state, read-only labels, Coordinator-only Permissions controls, capability combinations, separate dangerous permissions, revoke, and stale/expired state.
- [ ] **Step 2: Run focused UI tests** with `python -m unittest tests.test_cluster_page tests.test_nodes_connections -v` and confirm missing controls/callbacks.
- [ ] **Step 3: Add presentation-only controls** that emit semantic grant/revoke/share callbacks; do not put authorization decisions in widgets.
- [ ] **Step 4: Add explicit confirmation for cleanup and process termination** and ensure hidden controls do not replace protocol enforcement.
- [ ] **Step 5: Run focused tests and commit** as `feat: add cluster capability controls`.

### Task 5: Gate Developer Diagnostics

**Files:**
- Modify: `window.py`, `maintenance/ui/window_page_data.py`, `maintenance/ui/window_pages.py`, `maintenance/ui/diagnostics_page.py`
- Test: existing diagnostics/window tests and new developer-access tests

- [ ] **Step 1: Add failing tests** proving internal observation remains active while the Diagnostics route/export is unavailable in normal user mode.
- [ ] **Step 2: Define one explicit developer-mode seam** controlled by a non-default launch/build configuration; do not embed a default password in the binary.
- [ ] **Step 3: Require developer unlock before route registration/export** and show a clear developer-mode indicator after unlock. Keep captured snapshots bounded and secret-free.
- [ ] **Step 4: Run focused diagnostics/window tests** and commit as `feat: restrict diagnostics to developer mode`.

### Task 6: Regression and Compatibility Verification

**Files:**
- Modify: only tests/docs required by failures

- [ ] **Step 1: Run all focused protocol, lifecycle, role, node, UI, and diagnostics tests.** Expected: all pass.
- [ ] **Step 2: Run `ruff check .`; expected: no findings.
- [ ] **Step 3: Run `ruff format --check .`; expected: all files formatted.
- [ ] **Step 4: Run `pyright`; expected: no errors.
- [ ] **Step 5: Run `mypy --ignore-missing-imports .`; expected: no errors.
- [ ] **Step 6: Run `scripts/run_tests.sh`; expected: full suite passes with no regressions.
- [ ] **Step 7: Verify package contents** so developer-only diagnostics configuration is not accidentally exposed as a user feature, then inspect `git diff`, `git status`, and all commits included in the change.
- [ ] **Step 8: Commit any final focused fixes** without touching unrelated existing work.

## Self-Review

- Spec coverage: authority matrix, temporary sharing, scoped grants, target-side
  authorization, revocation, fencing, diagnostics gating, UI behavior, and test
  requirements each have a task.
- Compatibility: persisted grants are additive; temporary shares are runtime-only;
  existing role, lifecycle, failover, scheduler, executor, and safety owners stay
  authoritative.
- No placeholders or unresolved decisions remain.
- The Coordinator's in-cluster full authority is explicitly preserved, while
  Subcoordinator and outside-cluster access remain read-only by default.
