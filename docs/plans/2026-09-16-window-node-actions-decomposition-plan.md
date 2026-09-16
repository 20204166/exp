# Window Node Actions Decomposition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decompose `maintenance/ui/window_node_actions.py` into focused implementation modules while keeping its stable facade below 1000 lines and preserving behavior.

**Architecture:** Keep `maintenance.ui.window_node_actions` as the compatibility facade. Move role, pairing, connection, and permission responsibilities into an adjacent `window_node_actions_impl` package, passing controller dependencies and patched collaborators explicitly at call time. Do not alter controller state ownership, RPC/serialization contracts, or safety ordering.

**Tech Stack:** Python 3.12, Tkinter, `unittest`, Ruff, Pyright, Mypy, existing `AppCoordinator` and node/cluster domain models.

---

## File Structure

- Modify: `maintenance/ui/window_node_actions.py` — stable facade and compatibility aliases.
- Create: `maintenance/ui/window_node_actions_impl/__init__.py` — package documentation only.
- Create: `maintenance/ui/window_node_actions_impl/roles.py` — role mutations, role dispatch, invite creation, and cluster joining.
- Create: `maintenance/ui/window_node_actions_impl/pairing.py` — pairing state, provisioning, confirmation, rollback, and cancellation.
- Create: `maintenance/ui/window_node_actions_impl/connections.py` — manual/trusted node lifecycle, connection tests, and remote activation.
- Create: `maintenance/ui/window_node_actions_impl/permissions.py` — permission, color, rename, and trust-revocation actions.
- Test: existing `tests/test_window_nodes.py` and `tests/test_nodes_connections_page.py`; preserve their facade imports and patch paths.

## Contract Map

- Keep every current public function in `window_node_actions.py` importable.
- Keep `_pairing_confirmation` importable because `tests/test_nodes_connections_page.py` imports it directly.
- Preserve facade-level patching of `AuthenticatedNodeProvider`, `request_target_grant`, `confirm_target_pairing`, and `abort_target_pairing` by passing the facade’s current values into implementation calls.
- Keep all controller callbacks, generation checks, rollback paths, error strings, status strings, transport pinning, and operation keys unchanged.

## Facade Delegation Pattern

Use explicit wrappers rather than wildcard re-exports when a moved function
depends on a patchable facade symbol. For example, the facade keeps its current
signature and forwards the current module global:

```python
def request_target_grant(
    controller: Any,
    candidate: Any,
    grant: PeerGrantRecord,
    *,
    cancel_event: threading.Event | None = None,
) -> PairingTransaction | bool:
    return pairing.request_target_grant(
        controller,
        candidate,
        grant,
        cancel_event=cancel_event,
        provider_cls=AuthenticatedNodeProvider,
    )
```

The implementation function accepts that collaborator as an explicit keyword
dependency and never imports the facade. For patched pairing control functions,
the facade passes `request_target_grant`, `confirm_target_pairing`, and
`abort_target_pairing` into the pairing entry points. Functions whose existing
dependency is already an explicit argument retain that argument unchanged.
This prevents a new module boundary from bypassing existing test seams.

### Task 1: Add package skeleton and facade import plan

**Files:** create the package skeleton; modify only target imports after tests establish the baseline.

- [ ] Record the current focused baseline with `scripts/run_tests.sh tests.test_window_nodes tests.test_nodes_connections_page -v`.
- [ ] Create the package `__init__.py` containing only its module docstring; do not add a second public API.
- [ ] Search all imports, monkeypatches, and direct private-symbol references before moving code.
- [ ] Run `ruff check maintenance/ui/window_node_actions.py maintenance/ui/window_node_actions_impl` and the focused tests; expect no behavior change.
- [ ] Commit the package skeleton separately with `refactor: scaffold node action implementation package`.

### Task 2: Extract role and cluster operations

**Files:** create `roles.py`; modify `window_node_actions.py`; test existing role, invite, and join cases.

- [ ] Copy role implementations without semantic edits: `_role_state`, `_save_role_state`, `_propagate_capability_grants`, `_classify_role_dispatch`, `_remote_role_op`, `set_node_roles`, `pause_node`, `resume_node`, `remove_job_node`, `revoke_node`, `create_cluster_invite`, `join_cluster_via_invite`, and `_apply_cluster_join`.
- [ ] Keep `roles.py`’s provider and transport defaults compatible with current injectable arguments.
- [ ] Replace the moved facade definitions with wrappers that pass the facade’s current provider/transport values where existing tests patch them.
- [ ] Run `scripts/run_tests.sh tests.test_window_nodes -v`; expected result is all existing tests passing.
- [ ] Run `pyright maintenance/ui/window_node_actions.py maintenance/ui/window_node_actions_impl/roles.py`; expected result is zero new errors.
- [ ] Commit with `refactor: extract node role actions`.

### Task 3: Extract pairing lifecycle

**Files:** create `pairing.py`; modify facade; preserve pairing tests and private confirmation helper.

- [ ] Move `_PairingAttempt`, `_restore_pairing`, `_prepare_pairing`, `_finish_pairing`, `pair_discovered_node`, `pair_discovered_node_async`, `cancel_pairing`, `request_target_grant`, `confirm_target_pairing`, `abort_target_pairing`, `_schedule_pairing_abort`, and `_schedule_pairing_confirm` as one lifecycle unit.
- [ ] Keep `_pairing_confirmation` available from the facade and have pairing use the facade-supplied formatter or retain the formatter as the implementation’s explicit dependency.
- [ ] Forward patched provider, request, confirm, and abort collaborators from the facade at invocation time.
- [ ] Run `scripts/run_tests.sh tests.test_window_nodes tests.test_nodes_connections_page -v`; expected result is all existing tests passing.
- [ ] Commit with `refactor: extract node pairing lifecycle`.

### Task 4: Extract permissions and node connections

**Files:** create `permissions.py` and `connections.py`; modify facade.

- [ ] Move permission/color/rename/trust-revocation functions into `permissions.py`, preserving fail-closed saves and rollback behavior.
- [ ] Move manual-host, connection-test, open-node, and activation functions into `connections.py`, preserving coordinator keys, generation checks, TLS pinning, and callback ordering.
- [ ] Keep messagebox/simpledialog/provider/transport injection signatures unchanged at the facade boundary.
- [ ] Run the focused node tests after each module migration; expected result is all existing tests passing.
- [ ] Commit with `refactor: extract node connection actions`.

### Task 5: Final facade and validation

- [ ] Read the facade and every implementation module top to bottom; remove only imports made obsolete by extraction.
- [ ] Confirm `wc -l maintenance/ui/window_node_actions.py` is below 1000 and confirm no duplicate implementation remains outside the package.
- [ ] Run `scripts/run_tests.sh` and record the exact count.
- [ ] Run `ruff check .`, `ruff format --check .`, `pyright`, `mypy --ignore-missing-imports .`, and `git diff --check`.
- [ ] Classify unrelated baseline failures without modifying unrelated files.
- [ ] Review `git diff` for public API, callback-order, security, platform, and test-seam regressions.
- [ ] Commit the final facade cleanup with `refactor: finalize node action facade`.
