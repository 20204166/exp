# Window Node Actions Decomposition Design

**Goal:** Reduce `maintenance/ui/window_node_actions.py` below 1000 lines through
responsibility-based extraction without changing behavior or public seams.

**Stable boundary:** `maintenance.ui.window_node_actions` remains the import and
monkeypatch facade used by `window.py` and tests. Its public functions retain
their names, signatures, return values, exceptions, and callback behavior.

**Implementation structure:** Create the adjacent package
`maintenance/ui/window_node_actions_impl/` with focused modules:

- `roles.py`: role-state projection, fail-closed dispatch, role RPCs, and
  invite/join operations.
- `pairing.py`: pairing attempt state and synchronous/asynchronous target-grant
  lifecycle, including confirmation and rollback.
- `connections.py`: trusted/manual node lifecycle, connection testing, and
  remote activation.
- `permissions.py`: node permission, color, rename, and trust-revocation
  actions.
- `__init__.py`: package documentation and explicit internal exports only.

The facade forwards controller dependencies and facade-level patched symbols at
call time so existing tests that patch provider, grant, confirmation, or abort
seams continue to exercise the same behavior. Existing domain owners remain
canonical for `NodeId`, `RoleState`, `AppCoordinator`, transport construction,
capabilities, permissions, and serialized state.

**Safety:** Extraction preserves security checks, fail-closed remote dispatch,
TLS pinning, cancellation and generation checks, transaction ordering, rollback,
refresh/status ordering, platform behavior, and serialized/RPC contracts. No
new feature, component behavior, or controller state is introduced.

**Validation:** Run focused node-action tests after each extraction wave, then
`scripts/run_tests.sh`, `ruff check .`, `ruff format --check .`, `pyright`,
`mypy --ignore-missing-imports .`, and `git diff --check`. Preserve all existing
edge-case tests and detailed explanatory docstrings.
