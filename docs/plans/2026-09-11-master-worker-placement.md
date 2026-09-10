# Master/Worker Placement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one small, deterministic placement policy that selects an eligible execution node for explicitly movable jobs while keeping all current hardware, filesystem, process, and UI work on its logical target node.

**Architecture:** `PlacementPolicy` will be a pure decision component used by `AppCoordinator`; it filters immutable node views by hard constraints, then ranks only eligible candidates with a documented deterministic rule. The first release will classify every existing operation and implement no remote-movable job because the repository contains no safe pure-computation endpoint; target-bound work will use a single-target placement decision and existing providers. Authorization, transport, worker execution, refresh cadence, cancellation, generations, and Tk delivery remain owned by their existing components.

**Tech Stack:** Python 3, `dataclasses`, `enum`, `unittest`, existing `NodeRegistry`/`NodeContext`, `AppCoordinator`, authenticated remote protocol, Tk-thread delivery, Ruff, Pyright, Mypy.

---

## Repository Audit

The current repository provides these authoritative boundaries:

- `maintenance/nodes.py` owns `NodeId`, `NodeDescriptor`, `NodeContext`, `NodeRegistry`, trust states, capabilities, permissions, and node-qualified operation keys.
- `maintenance/remote.py` owns HMAC authentication, protocol validation, capability negotiation, target-side authorization, remote read providers, and bounded remote handlers.
- `maintenance/components/coordinator.py` owns `ComponentRefreshScheduler`, `ScanCoordinator`, and `AppCoordinator` generations, coalescing, cancellation, cached results, and delivery.
- `maintenance/components/node_selection.py` owns selected-node transitions and cancellation/render invalidation.
- `maintenance/diagnostics.py` and `maintenance/ui/diagnostics_page.py` already expose bounded component, operation, node, and render diagnostics.
- `maintenance/components/peer_connection.py` owns connection attempts and peer lifecycle; placement must consume its state rather than probe the network.
- `maintenance/components/catalog.py` describes current component capabilities but does not own scheduling or execution.
- `maintenance/dialogs.py`, `maintenance/scanner_support/`, and `maintenance/actions.py` implement target-bound reads and destructive actions.

Current job classification:

- **LOCAL-BOUND:** Tk/UI operations, local settings/persistence, local file-to-trash cleanup, and local-only window actions.
- **TARGET-BOUND:** CPU, memory, storage, GPU, network, battery, thermal, process enumeration, process termination, filesystem review, and any future hardware acquisition. Their data has meaning only on the target node.
- **MOVABLE:** none currently identified. Hashing supplied bytes, parsing supplied text, aggregation, compression, and report generation are not existing operations or remote contracts, so this release must not invent one.

The initiating System Analyzer instance is the request coordinator for a placement decision. It is not a security principal, permanent master server, or privileged authority. A worker is the selected node/provider for one explicitly typed operation. The target/provider remains the final authorization and safety boundary.

## File Map

- Create `maintenance/components/placement.py`: immutable job classifications, placement request/view/decision types, hard eligibility filtering, deterministic ranking, and explainable rejection/selection reasons. It has no Tk, transport, persistence, executor, or timer imports.
- Modify `maintenance/components/__init__.py`: re-export only the placement public types, matching the package's existing stable interface.
- Modify `maintenance/components/coordinator.py`: add a small dependency-composed placement hook that asks the policy for a decision before a placed run; preserve the existing `run`, generation, cancellation, coalescing, and delivery APIs unchanged.
- Keep `maintenance/nodes.py` unchanged: its existing descriptor, connection, trust, permission, and capability fields are sufficient input. The adapter belongs in `maintenance/components/placement.py` so the node model does not import its placement consumer.
- Modify `maintenance/diagnostics.py`: include one bounded latest placement diagnostic, including job type, selected worker, eligible count, and sanitized reason.
- Modify `maintenance/ui/diagnostics_page.py`: render the optional latest placement row using existing presentation primitives; do not add settings or manual worker controls.
- Create `tests/test_placement.py`: pure selector tests for eligibility, ranking, target locality, stale metrics, explanations, and no-candidate results.
- Modify `tests/test_components.py`: prove placement selection does not bypass AppCoordinator generations, cancellation, or delivery.
- Modify `tests/test_nodes.py`: prove placement views preserve node identity and target-qualified keys.
- Modify `tests/test_diagnostics.py` and `tests/test_diagnostics_page.py`: prove bounded placement diagnostics and empty-state rendering.
- Create `docs/MASTER_WORKER_PLACEMENT_2026-09-11.md`: record the implemented model, current zero-movable-job result, constraints, and future opportunities.

No change is planned for `ComponentRefreshScheduler`, `maintenance/remote.py` operation endpoints, `maintenance/actions.py`, or existing providers because none should become a placement owner or movable executor in this phase.

## Design Contract

The selector will use these types in `maintenance/components/placement.py`:

```python
class JobClass(str, Enum):
    LOCAL_BOUND = "local_bound"
    TARGET_BOUND = "target_bound"
    MOVABLE = "movable"


@dataclass(frozen=True, slots=True)
class PlacementRequest:
    operation: str
    job_class: JobClass
    target_node_id: NodeId | None
    required_capability: NodeCapability
    required_permission: NodePermission | None = None
    input_size_bytes: int = 0
    output_size_bytes: int = 0
    remote_transfer_threshold_bytes: int = 0


@dataclass(frozen=True, slots=True)
class PlacementView:
    node_id: NodeId
    is_local: bool
    trusted: bool
    authenticated: bool
    online: bool
    protocol_compatible: bool
    identity_valid: bool
    shutting_down: bool
    capabilities: frozenset[NodeCapability]
    permissions: frozenset[NodePermission]
    active_jobs: int = 0
    recent_latency_ms: float | None = None
    metrics_observed_at: float | None = None


@dataclass(frozen=True, slots=True)
class PlacementDecision:
    selected_node_id: NodeId | None
    eligible_node_ids: tuple[NodeId, ...]
    rejected: tuple[tuple[NodeId, str], ...]
    reason: str
```

Rules encoded by the policy:

1. `LOCAL_BOUND` selects only the local node and fails if that node is not eligible.
2. `TARGET_BOUND` selects only `target_node_id`; it never considers another node.
3. `MOVABLE` considers local and remote candidates after all hard filters.
4. Hard filters are trust, authentication, online state, protocol compatibility, identity validity, shutdown state, required capability, required permission, and target identity.
5. Unknown capability, missing permission, stale/unknown protocol, authentication failure, identity mismatch, offline state, and shutdown state reject a node; these are never soft ranking values.
6. Stale optional metrics are ignored for ranking, not converted into offline or unauthorized state. Use a single freshness constant of 30 seconds and an injected clock.
7. Movable ranking is: eligible local node when `input_size_bytes + output_size_bytes` is at or below the explicit byte threshold; otherwise lower active jobs, then fresh lower latency, then local preference, then stable `NodeId.value`. The reason states which rules actually decided the result and never claims global load optimization.
8. `input_size_bytes`, `output_size_bytes`, and `remote_transfer_threshold_bytes` must be non-negative integers. A movable request with non-zero transfer size and no known remote latency remains local unless a remote candidate is clearly better by active-job count and has a fresh latency value. No byte-to-time conversion or fake bandwidth estimate is allowed.
9. No selector result grants authorization. The selected provider/target validates the typed operation again.

## Implementation Tasks

### Task 1: Lock Down the Placement Contract

**Files:**
- Create: `maintenance/components/placement.py`
- Modify: `maintenance/components/__init__.py`
- Create: `tests/test_placement.py`

- [ ] **Step 1: Write failing enum and value-object tests.**

Add tests asserting the `JobClass` values, request validation for negative transfer sizes, immutable `PlacementView`, and a decision with no selected node when no candidate is eligible.

```python
def test_request_rejects_negative_transfer_sizes() -> None:
    with self.assertRaises(ValueError):
        PlacementRequest("hash", JobClass.MOVABLE, None, NodeCapability.COMPONENT_READ, input_size_bytes=-1)


def test_unknown_candidates_are_not_eligible() -> None:
    request = PlacementRequest(
        "hash", JobClass.MOVABLE, None, NodeCapability.COMPONENT_READ
    )
    view = PlacementView(
        NodeId("peer"), False, False, False, True, True, True, False,
        frozenset({NodeCapability.COMPONENT_READ}), frozenset(),
    )
    decision = PlacementPolicy(clock=lambda: 100.0).choose(
        request,
        (view,),
    )
    self.assertIsNone(decision.selected_node_id)
    self.assertEqual(decision.rejected[0][1], "not trusted")
```

- [ ] **Step 2: Run the focused tests and verify the expected import/implementation failure.**

Run: `python -m unittest tests.test_placement -v`

Expected: FAIL because `maintenance.components.placement` does not yet exist.

- [ ] **Step 3: Implement the value objects and policy skeleton.**

Define `JobClass`, `PlacementRequest`, `PlacementView`, `PlacementDecision`, `PlacementPolicy`, and a private `_is_fresh` helper. Give `PlacementPolicy` an injectable `clock` defaulting to `time.monotonic` so production callers need no timing setup while tests can use a fixed clock. Validate operation names, target requirements for local/target-bound jobs, non-negative integer sizes, and non-negative active-job counts. Keep the policy synchronous and side-effect free.

- [ ] **Step 4: Implement hard filtering and deterministic ranking.**

Return one rejection reason per excluded node. Filter in this order: target/local constraint, trusted, authenticated, online, protocol-compatible, identity-valid, not shutting down, capability, and permission. Rank only survivors using the contract above; sort ties by `NodeId.value`. Build a reason string from the selected rule and eligible count.

- [ ] **Step 5: Run the focused tests and add the complete matrix.**

Run: `python -m unittest tests.test_placement -v`

Add passing tests for offline, untrusted, unauthenticated, incompatible protocol, identity mismatch, shutdown, missing capability, missing permission, target mismatch, stale metrics, local-small-job preference, active-job ranking, latency ranking, stable tie-breaking, and explainable rejection/selection.

- [ ] **Step 6: Export the public types and commit.**

Re-export only `JobClass`, `PlacementDecision`, `PlacementPolicy`, `PlacementRequest`, `PlacementView`, and `placement_view_for_context` from `maintenance/components/__init__.py`.

```bash
git add maintenance/components/placement.py maintenance/components/__init__.py tests/test_placement.py
git commit -m "feat: add deterministic placement policy"
```

### Task 2: Build Placement Views Without Adding Authority

**Files:**
- Modify: `maintenance/components/placement.py`
- Modify: `tests/test_nodes.py`
- Modify: `tests/test_placement.py`

- [ ] **Step 1: Write the registry-to-view tests.**

Create local, trusted-online, offline, identity-mismatched, and discovered contexts. Assert that conversion preserves `NodeId`, capabilities, permissions, localness, and connection state; discovered nodes must have `trusted=False`; identity mismatch must have `identity_valid=False`.

```python
def test_discovered_context_cannot_become_a_placement_candidate() -> None:
    view = placement_view_for_context(_discovered_context())
    self.assertFalse(view.trusted)
    self.assertFalse(view.authenticated)
```

- [ ] **Step 2: Run the tests and verify the missing adapter failure.**

Run: `python -m unittest tests.test_nodes tests.test_placement -v`

Expected: FAIL because the placement-view adapter is not defined.

- [ ] **Step 3: Add the minimal adapter in `maintenance/components/placement.py`.**

Implement `placement_view_for_context(context, *, protocol_compatible=None, shutting_down=False, active_jobs=0, recent_latency_ms=None, metrics_observed_at=None)`. Treat local protocol compatibility as true when omitted and remote compatibility as false when omitted; the authenticated remote handshake must explicitly pass true. Derive `trusted` only from `NodeTrustState.TRUSTED` or `AUTHORISED`, `authenticated` only from `NodeConnectionStatus.ONLINE` for remote nodes, and local authentication from the local descriptor. Derive `online` from `NodeStatus.ONLINE` plus connection state, and reject `IDENTITY_CHANGED`/`MISMATCH` through `identity_valid`. Do not mutate the context. Re-export this adapter from `maintenance/components/__init__.py`.

- [ ] **Step 4: Run node and placement tests.**

Run: `python -m unittest tests.test_nodes tests.test_placement -v`

Expected: all selected tests pass, including the existing node trust and selection tests.

- [ ] **Step 5: Commit the adapter.**

```bash
git add maintenance/components/placement.py tests/test_nodes.py tests/test_placement.py
git commit -m "feat: expose safe node placement views"
```

### Task 3: Preserve AppCoordinator Lifecycle Semantics

**Files:**
- Modify: `maintenance/components/coordinator.py`
- Modify: `tests/test_components.py`

- [ ] **Step 1: Write a failing delegation test.**

Inject a fake policy and assert that `AppCoordinator.choose_placement(request, views)` delegates exactly once and returns the policy decision without starting work, creating an executor, or changing `AppRunState`.

```python
def test_choose_placement_does_not_start_or_mutate_a_run() -> None:
    expected = PlacementDecision(None, (), (), "no eligible nodes")
    request = PlacementRequest(
        "hash", JobClass.MOVABLE, None, NodeCapability.COMPONENT_READ
    )
    views = ()

    class FakePlacementPolicy:
        def choose(self, received_request, received_views):
            self.received = (received_request, received_views)
            return expected

    policy = FakePlacementPolicy()
    coordinator = AppCoordinator(placement_policy=policy, runner=lambda work: None)
    result = coordinator.choose_placement(request, views)
    self.assertIs(result, expected)
    self.assertFalse(coordinator.state("hash").in_flight)
```

- [ ] **Step 2: Run the focused coordinator test and verify the API failure.**

Run: `python -m unittest tests.test_components -v`

Expected: FAIL because `AppCoordinator` has no placement policy injection or `choose_placement` method.

- [ ] **Step 3: Add the dependency-composed seam.**

Add an optional `placement_policy: PlacementPolicy | None` constructor argument, defaulting to a new `PlacementPolicy()` only when callers do not inject one. Add `choose_placement(request, views)` as a synchronous delegation method. Do not alter `run`, `begin`, `_claim_run`, cancellation, generation checks, coalescing, runner invocation, delivery, or executor limits.

- [ ] **Step 4: Add lifecycle regression tests.**

Prove an existing keyed run still coalesces, cancellation still drops a late result, a second node-qualified key remains independent, and choosing placement does not create a second lifecycle or scheduler.

- [ ] **Step 5: Run the coordinator regression set.**

Run: `python -m unittest tests.test_components tests.test_multi_node_concurrency tests.test_lifecycle_stress -v`

Expected: all tests pass with no additional worker thread or executor created by placement.

- [ ] **Step 6: Commit the lifecycle seam.**

```bash
git add maintenance/components/coordinator.py tests/test_components.py tests/test_multi_node_concurrency.py tests/test_lifecycle_stress.py
git commit -m "feat: let app coordinator request placement decisions"
```

### Task 4: Prove Existing Operations Are Not Rerouted

**Files:**
- Modify: `tests/test_placement.py`
- Modify: `tests/test_nodes.py`
- Modify: `tests/test_remote_contract.py`
- Modify: `tests/test_process_table.py` and `tests/test_storage_dialog.py` where their current target seams are exercised

- [ ] **Step 1: Add target-bound placement tests.**

For a CPU read, process review, storage review, and process termination request with target `NodeId("node-b")`, provide eligible local, node B, and node C views. Assert every decision selects node B and that a request with a missing or mismatched target returns no candidate rather than selecting a fallback.

```python
def test_target_bound_process_action_never_moves_to_another_worker() -> None:
    from dataclasses import replace

    policy = PlacementPolicy(clock=lambda: 100.0)
    local_view = PlacementView(
        NodeId("local"), True, True, True, True, True, True, False,
        frozenset({NodeCapability.PROCESS_TERMINATION}),
        frozenset({NodePermission.PROCESS_TERMINATION}),
    )
    node_b_view = replace(local_view, node_id=NodeId("node-b"), is_local=False)
    node_c_view = replace(local_view, node_id=NodeId("node-c"), is_local=False)
    decision = policy.choose(
        PlacementRequest(
            "process_request_quit",
            JobClass.TARGET_BOUND,
            NodeId("node-b"),
            NodeCapability.PROCESS_TERMINATION,
            NodePermission.PROCESS_TERMINATION,
        ),
        (local_view, node_b_view, node_c_view),
    )
    self.assertEqual(decision.selected_node_id, NodeId("node-b"))
```

- [ ] **Step 2: Add authorization-boundary tests.**

Assert that discovered, trusted-but-unauthorized, capability-only, authentication-failed, identity-changed, revoked, and protocol-incompatible views cannot be selected. Assert that a selected decision does not alter descriptor permissions or remote grants; target-side `RemoteService` authorization tests remain green.

- [ ] **Step 3: Add node-key and stale-result tests.**

Assert that `node_operation_key(NodeId("node-a"), "analysis")` differs from node B's key, and that a late result delivered under node A's generation cannot be applied to node B's logical request. Reuse the existing `AppCoordinator` and render-generation test seams instead of adding another result cache.

- [ ] **Step 4: Run the target, security, and remote regressions.**

Run: `python -m unittest tests.test_placement tests.test_nodes tests.test_remote_contract tests.test_remote_security tests.test_process_table tests.test_storage_dialog tests.test_multi_node_concurrency -v`

Expected: all tests pass; no target-bound operation invokes a different node provider and no discovered/trusted-only node becomes executable.

- [ ] **Step 5: Commit the safety coverage.**

```bash
git add tests/test_placement.py tests/test_nodes.py tests/test_remote_contract.py tests/test_remote_security.py tests/test_process_table.py tests/test_storage_dialog.py tests/test_multi_node_concurrency.py
git commit -m "test: enforce target-bound placement safety"
```

### Task 5: Add Bounded Placement Diagnostics

**Files:**
- Modify: `maintenance/diagnostics.py`
- Modify: `maintenance/ui/diagnostics_page.py`
- Modify: `tests/test_diagnostics.py`
- Modify: `tests/test_diagnostics_page.py`

- [ ] **Step 1: Write the failing diagnostics projection test.**

Build a snapshot with one placement decision and assert serialization contains only job type, selected worker, eligible count, and the bounded reason. Assert a 160-character detail limit and no secrets, credentials, full request payloads, or node permission internals.

```python
def test_placement_diagnostic_is_bounded_and_sanitized() -> None:
    from types import SimpleNamespace

    decision = PlacementDecision(
        NodeId("node-a"), (NodeId("node-a"),), (), "selected node-a"
    )
    scheduler = SimpleNamespace(intervals={}, diagnostic_state=lambda _key: ())
    coordinator = SimpleNamespace(diagnostic_states=lambda: ())
    registry = SimpleNamespace(contexts=lambda: ())
    ui_coordinator = SimpleNamespace(
        pending_count=0,
        render_requests=0,
        render_commits=0,
        coalesced_requests=0,
        stale_rejections=0,
    )
    snapshot = build_diagnostics_snapshot(
        scheduler=scheduler,
        coordinator=coordinator,
        registry=registry,
        ui_coordinator=ui_coordinator,
        placement=decision,
    )
    payload = serialize_diagnostics(snapshot)
    self.assertIn("selected_worker", payload)
    self.assertNotIn("secret", payload.lower())
    self.assertIsNotNone(snapshot.placement)
    assert snapshot.placement is not None
    self.assertLessEqual(len(snapshot.placement.reason), 160)
```

- [ ] **Step 2: Run the focused diagnostics tests and verify the missing field failure.**

Run: `python -m unittest tests.test_diagnostics tests.test_diagnostics_page -v`

Expected: FAIL because `DiagnosticsSnapshot` has no placement field or page row.

- [ ] **Step 3: Add the optional bounded model field.**

Define `PlacementDiagnostic(job_type, selected_worker, eligible_count, reason)` in `maintenance/diagnostics.py`, truncate `job_type`, `selected_worker`, and `reason` to `MAX_DETAIL_LENGTH`, and add `placement: PlacementDiagnostic | None = None` to `DiagnosticsSnapshot`. Keep existing positional construction compatible by appending the field with a default.

- [ ] **Step 4: Thread the latest decision into diagnostics.**

Add an optional `placement` argument to `build_diagnostics_snapshot`. Do not persist a history, create a telemetry database, or expose auth details. `AppCoordinator` may supply only its latest bounded decision; an absent decision renders as no placement data.

- [ ] **Step 5: Render one diagnostics row and test empty state.**

Add a `Placement` row to the existing Summary or Running work section. Render `No placement decision yet` when absent and the decision's sanitized reason when present. Do not add settings, worker override controls, or new logging infrastructure.

- [ ] **Step 6: Run and commit diagnostics changes.**

Run: `python -m unittest tests.test_diagnostics tests.test_diagnostics_page tests.test_components -v`

```bash
git add maintenance/diagnostics.py maintenance/ui/diagnostics_page.py tests/test_diagnostics.py tests/test_diagnostics_page.py tests/test_components.py
git commit -m "feat: expose bounded placement diagnostics"
```

### Task 6: Document the Actual Architecture and Deliberate Limits

**Files:**
- Create: `docs/MASTER_WORKER_PLACEMENT_2026-09-11.md`

- [ ] **Step 1: Write the architecture document from implemented behavior.**

Include the coordinator/placement/providers diagram, explain that nodes remain independent, and distinguish coordinator role from authority. State that `ComponentRefreshScheduler` decides when, `PlacementPolicy` decides where, `AppCoordinator` owns lifecycle, and target providers own authorization and safety.

- [ ] **Step 2: Record the complete job classification.**

List local-bound UI/settings/actions, target-bound hardware/process/storage/cleanup operations, and the audited result that there are zero current movable jobs. Explicitly state that no remote compute endpoint was invented.

- [ ] **Step 3: Record constraints and failure semantics.**

Document trust/authentication/protocol/capability/permission/identity/online/shutdown filters, fresh optional metrics, deterministic tie-breaking, transfer threshold, no destructive retry/reroute, safe movable retry policy being unused because there are no movable jobs, coordinator disappearance, worker failure, revocation, node switching, and late-result behavior.

- [ ] **Step 4: Record deliberately unused mechanisms.**

State that the implementation does not add a `ResourceGovernor`, pressure sampler, reservation system, second scheduler, leader election, worker manager, arbitrary RPC, manual worker settings, telemetry database, or continuous network probing. Include the future opportunities: only explicitly typed pure hashing/parsing/aggregation/report jobs after a bounded remote contract exists.

- [ ] **Step 5: Review and commit the documentation.**

Verify every claim against the implementation and tests, then run `git diff --check`.

```bash
git add docs/MASTER_WORKER_PLACEMENT_2026-09-11.md
git diff --check
git commit -m "docs: define master worker placement boundaries"
```

### Task 7: Full Validation and Release Handoff

**Files:**
- No new application files; inspect the complete diff and all files listed above.

- [ ] **Step 1: Run the placement and architecture regression groups.**

Run: `python -m unittest tests.test_placement tests.test_nodes tests.test_components tests.test_remote_contract tests.test_remote_security tests.test_diagnostics tests.test_diagnostics_page tests.test_multi_node_concurrency tests.test_lifecycle_stress tests.test_peer_connection tests.test_discovery_end_to_end -v`

Expected: zero failures and no new warnings indicating cross-node result delivery, unauthorized selection, or unbounded worker creation.

- [ ] **Step 2: Run the full repository test suite.**

Run: `python -m unittest discover -s tests -v`

Expected: all discovered tests pass. If the environment emits the repository's known disk-persistence warning, record it separately and do not treat it as placement evidence.

- [ ] **Step 3: Run required static and hygiene checks.**

Run each command independently: `ruff check .`, `ruff format --check .`, `pyright`, `mypy --ignore-missing-imports`, `python -m compileall -q maintenance tests`, and `git diff --check`.

Expected: every installed check exits 0. If a tool is unavailable, report the exact missing command instead of claiming a pass.

- [ ] **Step 4: Audit forbidden architecture before release.**

Search the diff for `ResourceGovernor`, new `ThreadPoolExecutor`, timers, sockets, arbitrary command/function dispatch, process/file reroute code, and settings controls. Confirm the only new decision owner is `PlacementPolicy`, the only lifecycle owner remains `AppCoordinator`, the only cadence owner remains `ComponentRefreshScheduler`, and no worker touches Tk.

- [ ] **Step 5: Review the final working tree and commit only intended files.**

Run: `git status --short`, `git diff --stat`, and `git log --oneline -10`. Ensure the plan, implementation, tests, and architecture document are the only intended changes. Create the final commit with the repository's release convention after all prior task commits are reviewed.

- [ ] **Step 6: Prepare the final report.**

Report: current architecture; coordinator and worker definitions; all three job classes; genuinely movable job count; hard constraints; soft ranking; placement owner; AppCoordinator and capability/auth integration; metrics used and ignored; boundedness; transfer cost; retry/idempotency; revoke and failure behavior; diagnostics; changed files; exact test/static results; performance observations; limitations; future opportunities; and final working-tree status.

## Acceptance Checklist

- [ ] Coordinator is a request-scoped role, not a superuser or permanent server.
- [ ] Nodes remain independent; no shared RAM/CPU or automatic workload migration exists.
- [ ] Local-bound and target-bound operations cannot be selected for another node.
- [ ] No current operation is called movable without a typed, pure, bounded contract.
- [ ] Discovery, trust, authentication, authorization, capability, protocol, identity, online, and shutdown checks remain distinct.
- [ ] Eligibility is filtered before ranking; ranking is deterministic and explainable.
- [ ] Optional metrics obey freshness and are never converted into authority state.
- [ ] `AppCoordinator` owns generations, cancellation, coalescing, result delivery, and stale-result rejection.
- [ ] `ComponentRefreshScheduler` remains the sole cadence owner.
- [ ] No Tk work, destructive retry, arbitrary RPC, second executor hierarchy, or `ResourceGovernor` behavior is introduced.
- [ ] Diagnostics expose only bounded latest placement data and no credentials.
- [ ] Full established validation passes, or every unavailable/failing check is documented with its exact output.

## Self-Review Results

- **Spec coverage:** Tasks 1-2 cover typed classification, eligibility, capabilities, permissions, connection and identity state; Task 3 covers AppCoordinator integration and lifecycle; Task 4 covers target isolation, revocation, late results, and security; Task 5 covers diagnostics; Task 6 covers architecture and future boundaries; Task 7 covers concurrency, performance-oriented audits, static checks, and the final report.
- **Scope check:** This remains one bounded placement subsystem. It deliberately does not include a separate movable-job implementation because the audit found none, so no second plan is needed for a nonexistent workload.
- **Placeholder scan:** No implementation step uses TBD, TODO, or unspecified edge-case instructions. Test snippets use concrete constructors and existing fake-object shapes.
- **Type consistency:** `PlacementRequest`, `PlacementView`, `PlacementDecision`, `PlacementPolicy.choose`, `placement_view_for_context`, `AppCoordinator.choose_placement`, and `PlacementDiagnostic` retain the same names and fields throughout the plan.
