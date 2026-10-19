# Expra Connect Backend Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace System Analyzer's custom Connect/cluster production backend with `expra-connect` 1.9.0.1 while preserving current UI behavior and recoverably migrating persisted state.

**Architecture:** Provision the pinned universal wheel as a verified companion artifact in app builds/installers. Introduce a headless adapter around `ConnectRuntime`; migrate app startup, discovery, pairing, remote-provider integration, then cluster ownership in controlled cutovers, preserving app-owned scanning and SQLite history/standby. Keep legacy state untouched until conversion and acceptance are verified.

**Tech Stack:** Python >=3.10, setuptools/pip wheels, PowerShell and Bash installers, `expra_connect` 1.9.0.1, unittest, Ruff, Pyright, mypy.

---

## File map

### Build and release
- `pyproject.toml`, `requirements.txt`: pin `expra-connect==1.9.0.1`; make the checked-in universal wheel resolvable to developer installs through `--find-links dist` because the configured index does not provide it.
- `dist/expra_connect-1.9.0.1-py3-none-any.whl`: vendored companion input; preserve its verified bytes and record SHA-256 in release metadata.
- `maintenance/_release.py`: validate companion artifact identity, wheel tags, metadata version, and checksum; include it in artifact synchronization and source-change detection without treating the binary as app Python source.
- `install/_common.sh`, `install/_common.ps1`: shared lookup/validation/install helpers.
- `install/build.sh`, `install/build.ps1`: stage/check the companion wheel without mutating the sibling source checkout.
- `install/install.sh`, `install/install.ps1`, `install/upgrade.sh`, `install/upgrade.ps1`, `install/rollback.sh`, `install/rollback.ps1`: validate both local artifacts before mutation, then let pip resolve declared runtime dependencies from its configured index while installing the companion before the app wheel.
- `install/install-user.sh`, `install/install-user.ps1`: per-user/system install paths install the companion wheel alongside the app wheel.
- `install/install-online.sh`, `install/install-online.ps1`: download both wheels and verify checksums before installation.
- `dist/SHA256SUMS`: checksum manifest for published artifacts.
- `tests/test_release.py`, `tests/test_install_scripts.py`: artifact validation and installer contract tests.
- `README.md`: document the local wheel and third-party dependency resolution path for development and installation.

### Runtime integration
- `maintenance/connect_runtime.py` (new): application adapter; owns package runtime construction, callback marshaling boundary, package-to-app model conversion, and deterministic start/shutdown. Does not own Tk widgets.
- `maintenance/connect_state_migration.py` (new): pure, deterministic legacy-state conversion/validation; never deletes source files.
- `window.py`: compose adapter; preserve current UI, dialogs, and page contracts; route lifecycle and discovery/pairing operations through adapter.
- `maintenance/nodes.py`, `maintenance/remote.py`, `maintenance/cluster.py`: retain compatibility model/API surfaces where callers still require them; remove only production ownership after all callers use the adapter/package.
- `maintenance/ui/window_discovery.py` and the directly related node/cluster UI support modules: adapt callback and action wiring only; do not redesign UI.
- `tests/test_connect_runtime.py`, `tests/test_connect_state_migration.py`, `tests/test_window_nodes.py`, `tests/test_cluster_roles_persistence.py`, `tests/test_remote_contract.py`: adapter characterization, migration, and existing-contract coverage.
- `docs/REMOTE_CLUSTER_TRUE_FLOW.md`, `docs/SECURITY.md`, `docs/PLATFORM.md`, `AGENTS.md`: update only durable ownership/protocol statements after implementation and acceptance evidence.

## Phase 1 — Reproducible companion-wheel provisioning

### Task 1: Pin and verify the companion artifact

**Files:** `pyproject.toml`, `requirements.txt`, `maintenance/_release.py`, `tests/test_release.py`, `dist/expra_connect-1.9.0.1-py3-none-any.whl`, `dist/SHA256SUMS`.

- [x] **Step 1: Add failing release tests** for a valid 1.9.0.1 universal wheel, wrong version, non-universal tag, wrong distribution name, missing wheel, and checksum mismatch. Use temporary wheel ZIPs with minimal `METADATA` and `WHEEL` members; assert validation rejects malformed/mismatched metadata before any artifact manifest is rewritten.
- [x] **Step 2: Run focused tests and observe the expected failure:** `scripts/run_tests.sh tests.test_release -v`.
- [x] **Step 3: Implement one release-helper validation path** that reads ZIP metadata, requires distribution `expra-connect`, version `1.9.0.1`, `Root-Is-Purelib: true`, and a `py3-none-any` tag, and compares SHA-256 to the pinned expected digest. Make artifact synchronization include the app wheel and companion wheel in deterministic filename order. The companion wheel must not enter the app wheel's Python source manifest.
- [x] **Step 4: Declare exact runtime dependency** as `expra-connect==1.9.0.1` in project metadata and requirements. Ensure `pip install -r requirements.txt` resolves the companion wheel locally using a `--find-links dist` directive; verify this in a disposable venv. Add the local universal wheel to `dist/` from the sibling checkout only after independently verifying its metadata and calculating its digest; do not edit files in `/home/btn17/Downloads/expra-connect`.
- [x] **Step 5: Run release tests:** `scripts/run_tests.sh tests.test_release -v`; expect PASS, including rejection cases.
- [x] **Step 6: Run release verification against the real artifact:** `python3 -m maintenance._release sync-artifacts --package-dir .`; inspect `dist/SHA256SUMS` and, from `dist/`, verify both entries with `sha256sum -c SHA256SUMS`.

### Task 2: Make local and online installers install both wheels safely

**Files:** `install/_common.sh`, `install/_common.ps1`, `install/install.sh`, `install/install.ps1`, `install/upgrade.sh`, `install/upgrade.ps1`, `install/rollback.sh`, `install/rollback.ps1`, `install/install-user.sh`, `install/install-user.ps1`, `install/install-online.sh`, `install/install-online.ps1`, `tests/test_install_scripts.py`, `README.md`.

- [x] **Step 1: Add failing installer contract tests** using temporary directories and stub Python executables. Assert each path verifies both wheel hashes before pip is invoked, uses the local companion wheel rather than an index lookup for `expra-connect`, permits pip to resolve third-party dependencies from its configured index, installs the companion before the app wheel, and leaves the installed app unchanged when either wheel is missing or corrupt.
- [x] **Step 2: Run focused tests:** `scripts/run_tests.sh tests.test_install_scripts -v`; confirm the new contract tests fail against current scripts.
- [x] **Step 3: Implement shared Unix and PowerShell helper functions** to locate the exact companion filename, parse/verify the checksum manifest, and invoke pip first on the local companion wheel (allowing index resolution for its missing third-party dependencies) and then on the local app wheel. Preserve existing Python selection, venv/user-install behavior, no-admin policy, and rollback semantics.
- [x] **Step 4: Update build scripts** to require the validated companion artifact and include it in `dist/SHA256SUMS`; building must never install packages, bump dependency version, or access the sibling checkout implicitly.
- [x] **Step 5: Update standalone online installers** to download the manifest plus both exact artifact names into their existing temporary directory, verify both hashes before install, and clean only that temporary directory on exit.
- [x] **Step 6: Run focused checks:** `scripts/run_tests.sh tests.test_install_scripts -v`; run Bash syntax checks (`bash -n install/*.sh`) and PowerShell parser checks where `pwsh` exists. Expect no syntax errors and all installer contract tests PASS.
- [x] **Step 7: Exercise build/install in a disposable Linux venv** with `SA_PYTHON` pointing to that venv; verify `python -c 'import expra_connect; assert expra_connect.__version__ == "1.9.0.1"'` and the app console entry point. Do not replace the active environment's install.

### Task 3: Verify package metadata and public API from the pinned artifact

**Files:** `tests/test_connect_runtime.py` (initial API smoke coverage), `pyproject.toml`, `requirements.txt`.

- [x] **Step 1: Add a package API smoke test** that asserts the installed dependency version and imports `ConnectConfig`, `ConnectRuntime`, runtime status/state, and required app-facing types from their 1.9.0.1 public module paths.
- [x] **Step 2: Run the focused test** in the disposable venv and record the exact supported imports; do not infer 1.9.0.1 API from the newer sibling source tree.
- [x] **Step 3: Resolve only metadata/import mismatches** in app dependency declaration or test paths; do not change the sibling package.
- [x] **Step 4: Re-run:** `scripts/run_tests.sh tests.test_connect_runtime -v` and assert package version exactly `1.9.0.1`.

## Phase 2 — Characterize contracts and introduce runtime adapter

### Task 4: Capture existing UI/runtime behavior before cutover

**Files:** `tests/test_window_nodes.py`, `tests/test_remote_contract.py`, `tests/test_remote_server.py`, `tests/test_cluster_roles_persistence.py`, `tests/test_cluster_page.py`, `tests/test_connect_runtime.py`.

- [ ] **Step 1: Add characterization assertions** for startup failure preserving local dashboard availability, discovery never implying trust or cluster membership, pairing requiring the existing approval path, connection state remaining separate from trust and cluster state, shutdown stopping listeners, and UI updates delivered through the existing Tk scheduling path.
- [ ] **Step 2: Run each affected module** with `scripts/run_tests.sh <module> -v`; all baseline assertions must pass before adapter implementation.
- [ ] **Step 3: Record the current source of every state field** from `maintenance/remote.py`, `maintenance/cluster.py`, `maintenance/nodes.py`, `window.py`, and `maintenance/ui/window_discovery.py` in test names/fixtures; do not copy secrets or real user state into fixtures.

### Task 5: Implement safe legacy-state conversion

**Files:** `maintenance/connect_state_migration.py`, `tests/test_connect_state_migration.py`, `maintenance/cluster.py` (read/compatibility only unless a narrow adapter is needed).

- [ ] **Step 1: Add failing pure-function tests** using synthetic fixtures for empty state, stable local identity, paired/trusted peers, directional grants/permissions, discovery preference, cluster role assignments, epoch/lease, invites/admissions, and capability grants. Assert exact destination fields and distinguish TRUST, CLUSTER, and CONNECTION.
- [ ] **Step 2: Add failure tests** for malformed JSON, invalid enums/IDs, duplicate or conflicting peers, partial epoch/lease data, unsupported schema versions, and invalid grant data. Assert conversion fails closed and never writes, moves, truncates, or deletes source files.
- [ ] **Step 3: Implement deterministic in-memory conversion and strict validation** using the actual public `expra_connect.runtime.persistence` and cluster model APIs verified from the pinned wheel. Keep filesystem operations outside the pure conversion function; return explicit converted data plus migration status, never secret-bearing diagnostic strings.
- [ ] **Step 4: Implement a separate activation helper** that writes converted package state to a new staging location, reloads it through the package store, verifies required identity/trust/cluster invariants, then atomically promotes staged state while retaining byte-identical backups of every legacy input. Any failure leaves the old files and active configuration untouched.
- [ ] **Step 5: Run:** `scripts/run_tests.sh tests.test_connect_state_migration -v`; inspect temporary filesystem snapshots to prove source bytes remain unchanged on both success (backup retained) and failure.

### Task 6: Build the headless `ConnectRuntime` adapter

**Files:** `maintenance/connect_runtime.py`, `tests/test_connect_runtime.py`, `maintenance/nodes.py` only for narrow type conversion compatibility.

- [ ] **Step 1: Add failing adapter tests** with an injected runtime factory and fake callback delivery. Cover construction without starting network/Tk work, successful start, startup failure to offline/unavailable status, duplicate start, idempotent shutdown, shutdown after partial startup, callbacks marshaled through the injected UI delivery function, and conversion of discovered/trusted/connected package records into app node models.
- [ ] **Step 2: Run:** `scripts/run_tests.sh tests.test_connect_runtime -v`; verify tests fail because the adapter does not exist.
- [ ] **Step 3: Implement `ConnectRuntimeAdapter`** as a headless owner around the pinned package runtime. Keep constructor dependencies explicit (profile path/config, callback delivery, runtime factory); expose start, shutdown, status, discovery, pairing, and provider lookup through typed adapter methods. Do not expose fencing values in logs/errors/UI values.
- [ ] **Step 4: Add a runtime protocol/fake only if needed** for deterministic tests; do not duplicate package behavior in the fake. The package runtime remains the only production owner of identity, pairing, trust, discovery, transport, and remote providers.
- [ ] **Step 5: Run:** `scripts/run_tests.sh tests.test_connect_runtime -v`; then `ruff check maintenance/connect_runtime.py tests/test_connect_runtime.py` and `ruff format --check maintenance/connect_runtime.py tests/test_connect_runtime.py`.

## Phase 3 — Cut over Connect and remote-provider ownership

### Task 7: Wire window startup, callbacks, and shutdown through the adapter

**Files:** `window.py`, `maintenance/connect_runtime.py`, `maintenance/ui/window_discovery.py`, `tests/test_window_nodes.py`, `tests/test_window.py`.

- [ ] **Step 1: Add failing window integration tests** with fake master/runtime factory for runtime start after UI composition, graceful startup failure, callback delivery on the Tk thread, and exactly-once shutdown on close. Assert dashboard construction/scanning still succeeds when Connect cannot start.
- [ ] **Step 2: Run focused tests** and verify failures demonstrate the current direct backend wiring.
- [ ] **Step 3: Replace direct listener/discovery startup ownership** in `window.py` with adapter lifecycle calls at the same user-visible startup point. Preserve existing connection/pairing dialogs and callback wording. Keep app-owned scheduler, scanner, and UI controller unchanged.
- [ ] **Step 4: Route close and partial-construction cleanup** through idempotent adapter shutdown; ensure a failed `start()` cannot leave a listener/thread or prevent Tk teardown.
- [ ] **Step 5: Run:** `scripts/run_tests.sh tests.test_window_nodes -v` and `scripts/run_tests.sh tests.test_window -v`; assert all new lifecycle and legacy UI assertions pass.

### Task 8: Cut over remote nodes/providers without weakening authorization

**Files:** `maintenance/remote.py`, `maintenance/remote_support/`, `maintenance/connect_runtime.py`, `maintenance/ui/window_discovery.py`, `tests/test_remote_contract.py`, `tests/test_remote_security.py`, `tests/test_remote_server.py`, `tests/test_remote_compatibility.py`.

- [ ] **Step 1: Map package 1.9.0.1 request/provider APIs against current adapter contracts** from the actual wheel. Add failing compatibility tests for authenticated read operations, process-action confirmation/authorization, TLS identity/fingerprint checks, pairing approval, revoke, cancellation, malformed messages, replay/staleness, and no-log constraints.
- [ ] **Step 2: Implement app-to-package boundary conversions** in the adapter. Preserve app-owned process/file action confirmations and safe action implementations; do not expose a package operation that bypasses them.
- [ ] **Step 3: Switch production call sites** to package providers/runtime and retain `maintenance.remote` compatibility exports only where tests/external app imports require them. Do not run custom transport and package transport simultaneously.
- [ ] **Step 4: Search and prove ownership:** `rg -n 'RemoteSocketServer|NetworkDiscovery|AuthenticatedNodeProvider|ConnectRuntime' window.py maintenance`; production startup must construct only the adapter/package path.
- [ ] **Step 5: Run:** `scripts/run_tests.sh tests.test_remote_contract -v`, `scripts/run_tests.sh tests.test_remote_security -v`, `scripts/run_tests.sh tests.test_remote_server -v`, and `scripts/run_tests.sh tests.test_remote_compatibility -v`. Review captured logs/errors for secrets, private keys, or fencing token values.

## Phase 4 — Cut over cluster ownership and persistence

### Task 9: Characterize and adapt cluster state/role operations

**Files:** `maintenance/connect_runtime.py`, `maintenance/cluster.py`, `maintenance/ui/` cluster page/controller modules, `window.py`, `tests/test_cluster.py`, `tests/test_cluster_roles.py`, `tests/test_cluster_roles_persistence.py`, `tests/test_cluster_failover.py`, `tests/test_cluster_page.py`.

- [ ] **Step 1: Add package-backed characterization tests** for create/join/leave, coordinator/subcoordinator/worker roles, invites, grants, lease renewal, promotion/rejoin, stale epochs, fencing rejection, role authorization, and durable save/reload. Test fence-token presence only; never assert or print token values.
- [ ] **Step 2: Implement cluster adapter methods** against the pinned package cluster APIs, preserving app UI models and keeping cluster membership distinct from connection status and trust. Preserve bounded SQLite history and standby stores as app-owned services.
- [ ] **Step 3: Route cluster page/controller operations through the same `ConnectRuntimeAdapter`;** remove direct production mutation of the legacy `maintenance.cluster.Cluster` only after equivalent package-backed tests pass.
- [ ] **Step 4: Keep compatibility serializers/readers** where needed to recognize old schema and migration backups; do not silently rewrite old state on read.
- [ ] **Step 5: Run:** `scripts/run_tests.sh tests.test_cluster -v`, `scripts/run_tests.sh tests.test_cluster_roles -v`, `scripts/run_tests.sh tests.test_cluster_roles_persistence -v`, `scripts/run_tests.sh tests.test_cluster_failover -v`, and `scripts/run_tests.sh tests.test_cluster_page -v`.

### Task 10: Perform staged persistence activation and rollback verification

**Files:** `maintenance/connect_state_migration.py`, `maintenance/connect_runtime.py`, `window.py`, `tests/test_connect_state_migration.py`, `tests/test_window_nodes.py`.

- [ ] **Step 1: Add integration tests** starting with legacy fixtures and verify the runtime loads converted identity/trust/cluster state with original files backed up byte-for-byte.
- [ ] **Step 2: Add injected failures** at staging write, package reload, invariant verification, and promotion. Assert active state remains old and all legacy bytes remain available in every failure case.
- [ ] **Step 3: Enable migration only when the destination package state is absent** and a supported legacy state is present. Make repeat startup idempotent; if both destination and legacy exist, load destination and retain legacy backup without overwriting either.
- [ ] **Step 4: Run migration and lifecycle tests:** `scripts/run_tests.sh tests.test_connect_state_migration -v` and `scripts/run_tests.sh tests.test_window_nodes -v`.

## Phase 5 — Remove duplicate production ownership and verify

### Task 11: Remove obsolete production paths without breaking compatibility

**Files:** `maintenance/remote.py`, `maintenance/remote_support/`, `maintenance/cluster.py`, affected tests, `AGENTS.md`.

- [ ] **Step 1: Search all imports and construction sites** for legacy server, discovery, pairing, transport, remote provider, cluster mutation, and store ownership. Classify each reference as test compatibility, data migration, or production.
- [ ] **Step 2: Remove or deprecate only duplicate production implementations** after call sites have moved and contract tests exercise the package path. Keep serializers/migration and stable re-export surfaces needed by app tests/users.
- [ ] **Step 3: Add an ownership regression test** asserting window startup constructs one runtime adapter and no legacy network owner; verify compatibility imports still resolve where intentionally retained.
- [ ] **Step 4: Update `AGENTS.md` ownership description** and relevant canonical docs (`REMOTE_CLUSTER_TRUE_FLOW.md`, `SECURITY.md`, `PLATFORM.md`) from verified code only. Explicitly state physical two-node acceptance remains outstanding until actually performed.
- [ ] **Step 5: Run related tests** with `scripts/run_tests.sh tests.test_remote_contract -v`, `scripts/run_tests.sh tests.test_cluster_roles_persistence -v`, and `scripts/run_tests.sh tests.test_window_nodes -v`.

### Task 12: Full verification and platform acceptance handoff

**Files:** all changed files; `docs/REMOTE_CLUSTER_TRUE_FLOW.md`, `docs/PLATFORM.md`, `docs/SECURITY.md` for evidence recording only.

- [ ] **Step 1: Run complete tests:** `scripts/run_tests.sh`; expect the full discovered suite to pass.
- [ ] **Step 2: Run required static gates:** `ruff check .`, `ruff format --check .`, `pyright`, and `mypy --ignore-missing-imports .`. Fix touched findings; report any pre-existing unrelated baseline findings precisely rather than claiming clean.
- [ ] **Step 3: Build and verify universal app wheel** using `install/build.sh`; verify app and companion wheel names, metadata, and `sha256sum -c dist/SHA256SUMS`.
- [ ] **Step 4: Verify fresh install and rollback in disposable Linux venvs** using installer scripts; assert app and package versions, offline installation, startup, and rollback behavior.
- [ ] **Step 5: Prepare Windows acceptance artifacts** only; do not develop or run source/tests on Windows. Follow `docs/PLATFORM.md` for Windows black-box wheel install/runtime reporting and physical two-node security/cluster acceptance.
- [ ] **Step 6: Report automated evidence separately from physical acceptance.** Do not claim full remote-cluster validation until the documented two-node procedure has actually passed.

## Execution constraints

- **User direction (2026-10-18):** Pause before Phase 2 and all Connect/remote/discovery backend or UI refactoring. The user is updating the UI from Tk to Qt on another branch; do not touch those app surfaces until they explicitly authorize resuming after that work.

- Before the first Python edit, load `senior-python-engineering`; select general, security, persistence/serialization, async/concurrency, public API, and testing scopes as applicable. Use TDD: each behavior change begins with a failing test.
- Before any implementation, reread `AGENTS.md`, `docs/REMOTE_CLUSTER_TRUE_FLOW.md`, `docs/SYSTEM_ARCHITECTURE_REVIEW.md`, `docs/PLATFORM.md`, and `docs/SECURITY.md`; verify all package APIs against the pinned 1.9.0.1 wheel, not the sibling repository's newer source.
- Do not edit `/home/btn17/Downloads/expra-connect`. Do not overwrite or delete live user state. Use synthetic test fixtures and temporary directories for migration tests.
- Keep UI behavior, process/file safety boundaries, human approval, firewall policy, and all three distributed-state axes intact.
- Run `ruff check .` and `ruff format --check .` after Python edits; also run `pyright` and `mypy --ignore-missing-imports .` before relying on tests as validation evidence.
- Do not use worktree creation/removal to discard or obscure current workspace state; this checkout currently has no Git metadata, so commits and Git-based cleanliness checks are unavailable.
