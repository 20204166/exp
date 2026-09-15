# Node Toplevel Dialogs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add four additive `Toplevel` workflows for node connection, pairing, details, and dashboard sharing while preserving existing page, coordinator, authorization, and persistence behavior.

**Architecture:** Keep `NodesConnectionsPage` and `ClusterPage` inside the existing `PageRouter`. Add small presentation-only dialog adapters that receive immutable specs and callbacks. `AppWindow` owns dialog instances; existing controller callbacks remain the only owners of side effects and background operations.

**Tech Stack:** Python 3.10+, Tkinter/ttk, existing `maintenance.ui.layout` primitives, unittest headless widget fakes, `AppCoordinator` delivery paths.

---

## File Map

- Create `maintenance/ui/connection_dialog.py`: manual-host fields, local validation, and test/add callback dispatch.
- Create `maintenance/ui/pairing_dialog.py`: fingerprint review and explicit pair confirmation.
- Create `maintenance/ui/node_details_dialog.py`: immutable node inspection and existing action buttons.
- Create `maintenance/ui/sharing_dialog.py`: current share state and existing share/stop callback dispatch.
- Modify `maintenance/ui/nodes_connections.py`: route add/test/pair/details row actions to injected dialog-open callbacks while retaining current callback contracts.
- Modify `maintenance/ui/cluster_page.py`: route share action to an injected dialog-open callback.
- Modify `maintenance/ui/window_node_actions.py`: expose dialog-safe display/action specs only where existing page specs do not already provide them.
- Modify `window.py`: create, deduplicate, center, and destroy the four dialogs; wire existing callbacks and refresh methods.
- Modify `maintenance/ui/__init__.py`: export reusable dialog classes/specs if the project’s public UI surface requires it.
- Create or modify `tests/test_node_toplevel_dialogs.py`: headless dialog behavior and callback tests.
- Modify existing Nodes/Cluster controller tests only for routing assertions; do not weaken or replace existing behavior tests.

## Task 1: Establish Shared Dialog Contract

**Files:**
- Create `tests/test_node_toplevel_dialogs.py`.
- Create the four dialog module skeletons with typed callback/spec declarations.

- [ ] **Step 1: Add failing contract tests**

Test that each dialog accepts an injected parent, data, callbacks, and widget classes; invokes callbacks with the exact existing payloads; and has a single close operation. Use the repository’s recording widget fakes rather than a live Tk root.

```python
def test_connection_dialog_dispatches_manual_host_callback():
    calls = []
    dialog = ConnectionDialog(fake_parent(), on_add=lambda name, host, port: calls.append((name, host, port)))
    dialog.host_var.set("peer.local")
    dialog.port_var.set("8123")
    dialog.name_var.set("Peer")
    dialog.submit()
    assert calls == [("Peer", "peer.local", 8123)]
```

- [ ] **Step 2: Run the focused test and confirm the expected missing-symbol failure**

Run `python -m unittest tests.test_node_toplevel_dialogs -v`.

- [ ] **Step 3: Implement the smallest shared lifecycle helper**

Use `maintenance.ui.layout.dialog_shell` and `dialog_footer`; configure each window as a transient child of the supplied parent. Keep no worker, registry, transport, or persistence imports in dialog modules. Ensure `close()` destroys the window exactly once and all callback execution remains on the caller’s Tk thread.

- [ ] **Step 4: Run the focused tests and commit the contract**

Run `python -m unittest tests.test_node_toplevel_dialogs -v`; expected result is PASS. Commit with `git add maintenance/ui/*_dialog.py tests/test_node_toplevel_dialogs.py && git commit -m "feat: add node dialog contracts"`.

## Task 2: Add Connection And Pairing Dialogs

**Files:**
- Modify `maintenance/ui/connection_dialog.py`.
- Modify `maintenance/ui/pairing_dialog.py`.
- Modify `maintenance/ui/nodes_connections.py`.
- Modify `tests/test_node_toplevel_dialogs.py`.

- [ ] **Step 1: Add failing connection/pairing behavior tests**

Cover blank host, non-numeric/out-of-range port, optional port conversion, explicit pairing confirmation, fingerprint visibility, and cancellation without invoking `on_pair`.

```python
def test_connection_dialog_rejects_invalid_port_without_callback():
    calls = []
    dialog = ConnectionDialog(fake_parent(), on_add=lambda *args: calls.append(args))
    dialog.host_var.set("peer.local")
    dialog.port_var.set("70000")
    dialog.submit()
    assert calls == []
    assert "port" in dialog.status_text().lower()
```

- [ ] **Step 2: Run tests to confirm they fail for missing behavior**

Run `python -m unittest tests.test_node_toplevel_dialogs.ConnectionDialogTests tests.test_node_toplevel_dialogs.PairingDialogTests -v`.

- [ ] **Step 3: Implement minimal dialog behavior**

Connection dispatches the existing test callback with its node ID only, and dispatches `on_add_manual_host(display_name, host, port)` with the controller’s current argument order. Pairing displays stable identity and both fingerprints, then dispatches only `on_pair(node_id)` after confirmation. Do not implement pairing or connection work inside either dialog.

- [ ] **Step 4: Wire Nodes-page entry points without changing callback signatures**

Add optional dialog-open callbacks to `NodesConnectionsCallbacks`, defaulting to no-op compatibility lambdas. When `window.py` supplies an opener, the relevant page action opens the dialog; direct existing callbacks remain available for headless callers and compatibility fixtures. Route only the selected row/action to the opener; retain refresh and status callbacks.

- [ ] **Step 5: Run focused tests and commit**

Run `python -m unittest tests.test_node_toplevel_dialogs tests.test_nodes_connections -v`; expected result is PASS. Commit with `git add maintenance/ui/connection_dialog.py maintenance/ui/pairing_dialog.py maintenance/ui/nodes_connections.py tests/test_node_toplevel_dialogs.py && git commit -m "feat: add connection and pairing dialogs"`.

## Task 3: Add Node Details Dialog

**Files:**
- Modify `maintenance/ui/node_details_dialog.py`.
- Modify `maintenance/ui/nodes_connections.py`.
- Modify `tests/test_node_toplevel_dialogs.py`.

- [ ] **Step 1: Add failing details tests**

Verify identity, host, port, pairing state, target state, role, and permissions are rendered from `TrustedNodeSpec`/`DiscoveredPeerSpec`; verify unavailable actions are not created and available actions invoke existing callbacks with the node ID.

```python
def test_details_dialog_does_not_show_disallowed_actions():
    dialog = NodeDetailsDialog(fake_parent(), spec=trusted_spec(openable=False), callbacks=callbacks())
    assert dialog.action("open") is None
```

- [ ] **Step 2: Run tests and confirm the expected failure**

Run `python -m unittest tests.test_node_toplevel_dialogs.NodeDetailsDialogTests -v`.

- [ ] **Step 3: Implement read-only details and callback-backed actions**

Use supplied immutable spec data. Show permissions as display data only. Gate action buttons using existing `selectable`, `openable`, `paused`, `role_editable`, and active-job fields. Each action calls its injected callback and then leaves refresh/authorization to the controller.

- [ ] **Step 4: Wire trusted/manual/discovered row detail actions**

Add one optional `on_details` callback to `NodesConnectionsCallbacks`; default it to a no-op. Pass the selected spec to `window.py` through the existing page refresh data path. Do not copy registry state into the dialog.

- [ ] **Step 5: Run focused tests and commit**

Run `python -m unittest tests.test_node_toplevel_dialogs tests.test_nodes_connections -v`; expected result is PASS. Commit with `git add maintenance/ui/node_details_dialog.py maintenance/ui/nodes_connections.py tests/test_node_toplevel_dialogs.py && git commit -m "feat: add node details dialog"`.

## Task 4: Add Sharing Dialog

**Files:**
- Modify `maintenance/ui/sharing_dialog.py`.
- Modify `maintenance/ui/cluster_page.py`.
- Modify `tests/test_node_toplevel_dialogs.py`.

- [ ] **Step 1: Add failing sharing tests**

Verify inactive state offers the existing share callback, active state offers the existing stop behavior, and closing does not invoke either callback.

```python
def test_sharing_dialog_confirm_uses_existing_callback():
    calls = []
    dialog = SharingDialog(fake_parent(), active=False, on_share=lambda: calls.append("share"), on_stop=lambda: calls.append("stop"))
    dialog.confirm()
    assert calls == ["share"]
```

- [ ] **Step 2: Run tests and confirm the expected failure**

Run `python -m unittest tests.test_node_toplevel_dialogs.SharingDialogTests -v`.

- [ ] **Step 3: Implement the fixed five-minute sharing presentation**

Display current state and the existing five-minute duration. Dispatch the supplied share/stop callbacks only; do not add a duration model or timer. Keep the dialog open until the controller’s normal state refresh closes or updates it.

- [ ] **Step 4: Route the Cluster-page share control to the dialog opener**

Add an optional dialog-open callback with a no-op default. Preserve the current `on_share_dashboard` callback for direct compatibility and ensure local-only visibility remains unchanged.

- [ ] **Step 5: Run focused tests and commit**

Run `python -m unittest tests.test_node_toplevel_dialogs tests.test_cluster_page -v`; expected result is PASS. Commit with `git add maintenance/ui/sharing_dialog.py maintenance/ui/cluster_page.py tests/test_node_toplevel_dialogs.py && git commit -m "feat: add dashboard sharing dialog"`.

## Task 5: Compose Dialogs In AppWindow

**Files:**
- Modify `window.py`.
- Modify `maintenance/ui/window_node_actions.py` only if an existing callback adapter is required.
- Modify controller routing tests.

- [ ] **Step 1: Add failing composition tests**

Assert each opener creates at most one transient dialog, passes the existing controller callback, and clears its reference after destruction. Assert opening dialogs does not replace the page router or coordinator.

- [ ] **Step 2: Run tests and confirm missing opener behavior**

Run `python -m unittest tests.test_window_nodes tests.test_window -v`.

- [ ] **Step 3: Implement four controller-owned openers**

Store dialog references on `AppWindow`, reuse an existing live instance, pass `self.master` as parent, and use `destroy` callbacks to clear references. Supply immutable page specs and existing callbacks. Keep all operations routed through current controller methods and existing coordinator delivery.

- [ ] **Step 4: Connect Nodes/Cluster callback factories**

Supply dialog opener callbacks from the composition root when constructing pages. Leave all callback defaults intact for headless callers and historical tests.

- [ ] **Step 5: Run controller tests and commit**

Run `python -m unittest tests.test_window_nodes tests.test_window -v`; expected result is PASS. Commit with `git add window.py maintenance/ui/window_node_actions.py tests && git commit -m "feat: compose node dialogs in app window"`.

## Task 6: Final Validation

- [ ] **Step 1: Review the complete diff**

Run `git diff --stat`, `git diff --check`, and `git status --short`; confirm only the approved dialog implementation, tests, and plan/spec changes are staged or committed. Do not add `docs/performance/observability/`.

- [ ] **Step 2: Run focused and full tests**

Run `python -m unittest tests.test_node_toplevel_dialogs tests.test_nodes_connections tests.test_cluster_page tests.test_window_nodes tests.test_window -v`, then `scripts/run_tests.sh`.

- [ ] **Step 3: Run static gates**

Run `ruff check .`, `ruff format --check .`, `pyright`, and `mypy --ignore-missing-imports`. Record any pre-existing environment failure without calling it a pass.

- [ ] **Step 4: Run BugGuard Mode A review gates**

Run `./lr impact`, `./lr 7`, and `./lr secrets` if available. Review the patch for unchanged callback signatures, no second `Tk()`, no worker/coordinator changes, no authorization bypass, and no dialog updates after destruction.

- [ ] **Step 5: Commit final validation adjustments**

Commit only fixes required by the validation results with a concise message matching the repository style. Do not rebuild the wheel unless separately requested.
