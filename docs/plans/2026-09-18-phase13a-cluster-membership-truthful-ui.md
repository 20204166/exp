# Phase 13A — Cluster Membership: Truthful UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface accurate cluster membership state in both the Nodes & Connections page and the All Systems page, and prevent the "Join Cluster" button from appearing for nodes already in the cluster.

**Architecture:** Three presentation-only files receive minimal, additive changes. A new `is_cluster_member: bool` field is added to both spec dataclasses. Spec-builder functions in `node_specs.py` derive membership from `ClusterState.role_assignments` (the canonical source). UI rendering methods consume the new field. No protocol, persistence, or transport layer is touched.

**Tech Stack:** Python 3.12, tkinter, frozen dataclasses (`@dataclass(frozen=True, slots=True)`), `pytest`, `ruff`, `pyright`

---

## File Structure

| File | Change |
|---|---|
| `maintenance/ui/nodes_connections.py` | Add `is_cluster_member: bool = False` to `TrustedNodeSpec`; update `_trusted_meta_text()` |
| `maintenance/ui/cluster_page.py` | Add `is_cluster_member: bool = False` to `ClusterNodeSpec`; guard Join Cluster button; fix `_meta_text()` non-member label |
| `maintenance/ui/window_supports/node_specs.py` | Populate `is_cluster_member` in `trusted_node_specs()` and `cluster_node_specs()`; fix `cluster_node_specs()` role source from `descriptor.role` → `role_assignments` |

Tests live in the existing test files that cover these modules (search: `tests/` for files that import `nodes_connections`, `cluster_page`, or `node_specs`).

---

## Task 1: Add `is_cluster_member` to spec dataclasses

**Files:**
- Modify: `maintenance/ui/nodes_connections.py:102-128` (`TrustedNodeSpec`)
- Modify: `maintenance/ui/cluster_page.py:54-75` (`ClusterNodeSpec`)

- [ ] **Step 1: Write the failing test for TrustedNodeSpec**

Find the test file that constructs `TrustedNodeSpec` (search: `grep -r "TrustedNodeSpec" tests/ -l`). Add:

```python
def test_trusted_node_spec_has_is_cluster_member_default_false():
    spec = TrustedNodeSpec(
        node_id="n1", display_name="Node", hostname="h", color=None,
        status="online", host="h", port=None, selectable=True,
    )
    assert spec.is_cluster_member is False
```

- [ ] **Step 2: Run to verify it fails**

```bash
pytest tests/ -k "test_trusted_node_spec_has_is_cluster_member" -v
```
Expected: `AttributeError: 'TrustedNodeSpec' object has no attribute 'is_cluster_member'`

- [ ] **Step 3: Add field to TrustedNodeSpec**

In `maintenance/ui/nodes_connections.py`, after `retry_automatic: bool = True` (line 128), add:

```python
    is_cluster_member: bool = False
```

- [ ] **Step 4: Write failing test for ClusterNodeSpec**

```python
def test_cluster_node_spec_has_is_cluster_member_default_false():
    spec = ClusterNodeSpec(
        node_id="n1", display_name="Node", hostname="h", color=None,
        trust="trusted", status="online", capabilities=(), is_local=False,
        selectable=True,
    )
    assert spec.is_cluster_member is False
```

- [ ] **Step 5: Run to verify it fails**

```bash
pytest tests/ -k "test_cluster_node_spec_has_is_cluster_member" -v
```

- [ ] **Step 6: Add field to ClusterNodeSpec**

In `maintenance/ui/cluster_page.py`, after `share_active: bool = False` (line 74), add:

```python
    is_cluster_member: bool = False
```

- [ ] **Step 7: Run both tests to verify they pass**

```bash
pytest tests/ -k "is_cluster_member_default" -v
```
Expected: 2 passed

- [ ] **Step 8: Commit**

```bash
git add maintenance/ui/nodes_connections.py maintenance/ui/cluster_page.py
git commit -m "$(cat <<'EOF'
feat(ui): add is_cluster_member field to TrustedNodeSpec and ClusterNodeSpec

Both spec dataclasses gain a bool field (default False) for downstream
rendering to distinguish paired-but-not-joined from active cluster members.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01ERfMzTT9xZTwHph6QHwqvw
EOF
)"
```

---

## Task 2: Populate `is_cluster_member` in `trusted_node_specs()`

**Files:**
- Modify: `maintenance/ui/window_supports/node_specs.py:66-112`

- [ ] **Step 1: Write the failing tests**

Find the test file covering `trusted_node_specs` (search: `grep -r "trusted_node_specs" tests/ -l`). Add three tests:

```python
def test_trusted_node_specs_non_member_is_cluster_member_false(registry, cluster_state_no_assignments):
    # cluster_state with empty role_assignments
    specs = trusted_node_specs(registry, cluster_state_no_assignments)
    assert all(not s.is_cluster_member for s in specs)

def test_trusted_node_specs_active_member_is_cluster_member_true(registry, cluster_state_with_worker):
    # cluster_state where the node has a non-revoked WORKER assignment
    specs = trusted_node_specs(registry, cluster_state_with_worker)
    member_specs = [s for s in specs if s.node_id == "worker-node-id"]
    assert len(member_specs) == 1
    assert member_specs[0].is_cluster_member is True

def test_trusted_node_specs_revoked_member_is_cluster_member_false(registry, cluster_state_revoked):
    # cluster_state where the node's assignment has revoked=True
    specs = trusted_node_specs(registry, cluster_state_revoked)
    revoked_specs = [s for s in specs if s.node_id == "revoked-node-id"]
    assert len(revoked_specs) == 1
    assert revoked_specs[0].is_cluster_member is False
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/ -k "trusted_node_specs_member" -v
```
Expected: 3 failed (field exists but not populated, so all False currently)

- [ ] **Step 3: Populate is_cluster_member in trusted_node_specs()**

In `maintenance/ui/window_supports/node_specs.py`, inside the `specs.append(ui_nodes.TrustedNodeSpec(...))` call (after `retry_automatic=context.retry.automatic_retry,`), add:

```python
                is_cluster_member=(
                    assignment is not None and not assignment.revoked
                ),
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/ -k "trusted_node_specs_member" -v
```
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add maintenance/ui/window_supports/node_specs.py
git commit -m "$(cat <<'EOF'
feat(ui): populate is_cluster_member in trusted_node_specs

Derives membership from ClusterState.role_assignments; revoked assignments
correctly yield is_cluster_member=False.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01ERfMzTT9xZTwHph6QHwqvw
EOF
)"
```

---

## Task 3: Fix `cluster_node_specs()` — `is_cluster_member` + role source

**Files:**
- Modify: `maintenance/ui/window_supports/node_specs.py:161-237`

This task has two sub-fixes: (a) populate `is_cluster_member`; (b) fix `role=descriptor.role` to use `role_assignments` when available.

- [ ] **Step 1: Write the failing tests**

```python
def test_cluster_node_specs_non_member_is_cluster_member_false(registry, cluster_state_no_assignments):
    specs = cluster_node_specs(registry, cluster_state=cluster_state_no_assignments)
    non_local = [s for s in specs if not s.is_local]
    assert all(not s.is_cluster_member for s in non_local)

def test_cluster_node_specs_active_member_is_cluster_member_true(registry, cluster_state_with_worker):
    specs = cluster_node_specs(registry, cluster_state=cluster_state_with_worker)
    member_specs = [s for s in specs if s.node_id == "worker-node-id"]
    assert member_specs[0].is_cluster_member is True

def test_cluster_node_specs_role_comes_from_role_assignments_not_descriptor(registry, cluster_state_coordinator):
    # cluster_state where local node has COORDINATOR role in role_assignments
    # but descriptor.role might differ
    specs = cluster_node_specs(registry, cluster_state=cluster_state_coordinator)
    local_specs = [s for s in specs if s.is_local]
    assert local_specs[0].role == "coordinator"
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/ -k "cluster_node_specs_member or cluster_node_specs_role" -v
```

- [ ] **Step 3: Apply both fixes in cluster_node_specs()**

In `maintenance/ui/window_supports/node_specs.py`, replace the `role=descriptor.role,` line (line ~209) and add `is_cluster_member`, inside the `specs.append(ui_cluster.ClusterNodeSpec(...))` block:

Replace:
```python
                role=descriptor.role,
```

With:
```python
                role=(
                    "coordinator"
                    if assignment is not None
                    and not assignment.revoked
                    and any(r.value == "coordinator" for r in assignment.roles)
                    else "subcoordinator"
                    if assignment is not None
                    and not assignment.revoked
                    and any(r.value == "subcoordinator" for r in assignment.roles)
                    else "worker"
                    if assignment is not None and not assignment.revoked
                    else descriptor.role
                ),
                is_cluster_member=(
                    assignment is not None and not assignment.revoked
                ),
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/ -k "cluster_node_specs" -v
```
Expected: all pass

- [ ] **Step 5: Run full suite to check for regressions**

```bash
pytest --tb=short -q
```
Expected: all pass (1930+)

- [ ] **Step 6: Commit**

```bash
git add maintenance/ui/window_supports/node_specs.py
git commit -m "$(cat <<'EOF'
fix(ui): cluster_node_specs — derive role and membership from role_assignments

Previously role used descriptor.role (discovery metadata), which could
diverge from the cluster's actual assignment. Now role_assignments is the
authoritative source; descriptor.role is a fallback for non-members only.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01ERfMzTT9xZTwHph6QHwqvw
EOF
)"
```

---

## Task 4: Update `_trusted_meta_text()` to show cluster membership

**Files:**
- Modify: `maintenance/ui/nodes_connections.py:701-712`

- [ ] **Step 1: Write the failing tests**

```python
def test_trusted_meta_text_non_member_shows_not_in_cluster(page):
    spec = make_trusted_spec(is_cluster_member=False, connection_status="online")
    text = page._trusted_meta_text(spec)
    assert "Not in cluster" in text
    assert "Worker" not in text

def test_trusted_meta_text_worker_member_shows_worker(page):
    spec = make_trusted_spec(is_cluster_member=True, role="worker", connection_status="online")
    text = page._trusted_meta_text(spec)
    assert "Worker" in text
    assert "Not in cluster" not in text

def test_trusted_meta_text_coordinator_member_shows_coordinator(page):
    spec = make_trusted_spec(is_cluster_member=True, role="coordinator", connection_status="online")
    text = page._trusted_meta_text(spec)
    assert "Coordinator" in text
    assert "Not in cluster" not in text
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/ -k "trusted_meta_text" -v
```

- [ ] **Step 3: Update _trusted_meta_text()**

In `maintenance/ui/nodes_connections.py`, replace the `_trusted_meta_text` method body:

Replace:
```python
    def _trusted_meta_text(self, spec: TrustedNodeSpec) -> str:
        conn_label = node_presentation.connection_status_label(
            spec.connection_status,
            manual_disconnected=spec.manual_disconnected,
            retry_automatic=spec.retry_automatic,
        )
        role_status = f"{node_presentation.trust_label('trusted')} · {conn_label}"
        if spec.target_state != "Unknown":
            role_status += f" · {spec.target_state}"
        if spec.identity_status == "mismatch":
            role_status += " · Identity mismatch"
        return role_status
```

With:
```python
    def _trusted_meta_text(self, spec: TrustedNodeSpec) -> str:
        conn_label = node_presentation.connection_status_label(
            spec.connection_status,
            manual_disconnected=spec.manual_disconnected,
            retry_automatic=spec.retry_automatic,
        )
        if spec.is_cluster_member:
            membership = spec.role.title()
        else:
            membership = "Not in cluster"
        role_status = f"{node_presentation.trust_label('trusted')} · {membership} · {conn_label}"
        if spec.target_state != "Unknown":
            role_status += f" · {spec.target_state}"
        if spec.identity_status == "mismatch":
            role_status += " · Identity mismatch"
        return role_status
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/ -k "trusted_meta_text" -v
```

- [ ] **Step 5: Commit**

```bash
git add maintenance/ui/nodes_connections.py
git commit -m "$(cat <<'EOF'
feat(ui): show cluster membership in Nodes & Connections meta label

Trusted peers now show their role (Coordinator/Worker) or "Not in cluster"
between the trust badge and the connection status label.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01ERfMzTT9xZTwHph6QHwqvw
EOF
)"
```

---

## Task 5: Guard Join Cluster button with `is_cluster_member`

**Files:**
- Modify: `maintenance/ui/cluster_page.py:358-370`

- [ ] **Step 1: Write the failing tests**

```python
def test_join_cluster_button_hidden_for_cluster_member(page):
    spec = make_cluster_spec(trust="trusted", is_local=False, is_cluster_member=True)
    row = page._node_row(body_frame, spec)
    assert not _has_button_text(row, "Join Cluster")

def test_join_cluster_button_shown_for_non_member(page):
    spec = make_cluster_spec(trust="trusted", is_local=False, is_cluster_member=False)
    row = page._node_row(body_frame, spec)
    assert _has_button_text(row, "Join Cluster")

def test_join_cluster_button_hidden_for_local_node(page):
    spec = make_cluster_spec(trust="trusted", is_local=True, is_cluster_member=False)
    row = page._node_row(body_frame, spec)
    assert not _has_button_text(row, "Join Cluster")
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/ -k "join_cluster_button" -v
```

- [ ] **Step 3: Add is_cluster_member guard**

In `maintenance/ui/cluster_page.py`, replace:

```python
        if (
            not spec.is_local
            and spec.trust in ("trusted", "authorised")
            and on_join_cluster is not None
        ):
```

With:

```python
        if (
            not spec.is_local
            and spec.trust in ("trusted", "authorised")
            and not spec.is_cluster_member
            and on_join_cluster is not None
        ):
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/ -k "join_cluster_button" -v
```

- [ ] **Step 5: Commit**

```bash
git add maintenance/ui/cluster_page.py
git commit -m "$(cat <<'EOF'
fix(ui): hide Join Cluster button for nodes already in cluster

Previously the button appeared for every trusted peer. Now it is suppressed
when is_cluster_member is True, preventing a confusing re-join attempt.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01ERfMzTT9xZTwHph6QHwqvw
EOF
)"
```

---

## Task 6: Fix All Systems `_meta_text()` non-member label

**Files:**
- Modify: `maintenance/ui/cluster_page.py:408-426` (`_meta_text`)

- [ ] **Step 1: Write the failing tests**

```python
def test_meta_text_non_member_trusted_shows_not_in_cluster(page):
    spec = make_cluster_spec(trust="trusted", is_local=False, is_cluster_member=False, role="worker")
    text = page._meta_text(spec)
    assert "Not in cluster" in text
    assert "Worker" not in text  # must not appear when not a member

def test_meta_text_worker_member_shows_worker(page):
    spec = make_cluster_spec(trust="trusted", is_local=False, is_cluster_member=True, role="worker")
    text = page._meta_text(spec)
    assert "Worker" in text
    assert "Not in cluster" not in text

def test_meta_text_local_node_shows_role_regardless(page):
    # Local node is always "in" its own cluster; no "Not in cluster" label
    spec = make_cluster_spec(trust="trusted", is_local=True, is_cluster_member=True, role="coordinator")
    text = page._meta_text(spec)
    assert "Coordinator" in text
    assert "Not in cluster" not in text
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/ -k "meta_text_non_member or meta_text_worker_member or meta_text_local" -v
```

- [ ] **Step 3: Update _meta_text()**

In `maintenance/ui/cluster_page.py`, replace:

```python
        meta += f" · {spec.role.title()}"
```

With:

```python
        if not spec.is_local and not spec.is_cluster_member:
            meta += " · Not in cluster"
        else:
            meta += f" · {spec.role.title()}"
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/ -k "meta_text" -v
```

- [ ] **Step 5: Run full suite**

```bash
pytest --tb=short -q
```
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add maintenance/ui/cluster_page.py
git commit -m "$(cat <<'EOF'
feat(ui): All Systems shows Not in cluster for trusted non-member peers

Previously all trusted nodes showed Worker (the role default) even when
not enrolled in role_assignments. Non-local non-members now show
"Not in cluster" so the distinction is unambiguous.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01ERfMzTT9xZTwHph6QHwqvw
EOF
)"
```

---

## Task 7: Final lint + full suite verification

- [ ] **Step 1: ruff**

```bash
ruff check .
```
Expected: no errors

- [ ] **Step 2: pyright**

```bash
pyright maintenance/ui/nodes_connections.py maintenance/ui/cluster_page.py maintenance/ui/window_supports/node_specs.py
```
Expected: 0 errors

- [ ] **Step 3: git diff --check**

```bash
git diff --check HEAD~6
```
Expected: no whitespace errors

- [ ] **Step 4: Full suite one final time**

```bash
pytest --tb=short -q
```
Expected: all pass (1930+)

---

## Self-Review

**Spec coverage:**
- §1 Membership owner — Tasks 2, 3 derive from `role_assignments` ✓
- §2 Pair ≠ join — no changes to pair path; confirmed not coupled ✓
- §3 N&C label — Task 4 updates `_trusted_meta_text()` ✓
- §4 All Systems label — Task 6 updates `_meta_text()` ✓
- §5 Join button guard — Task 5 guards with `is_cluster_member` ✓
- §6 `cluster_node_specs` role source fix — Task 3b ✓
- §8 Regression: Join button double-fire — Task 5 closes it ✓
- §8 Regression: non-member Worker label — Tasks 4, 6 close it ✓

**Placeholder scan:** None found.

**Type consistency:** `is_cluster_member: bool` added in Tasks 1, consumed as `spec.is_cluster_member` in Tasks 4, 5, 6. `assignment.revoked` used as in existing code in `promote_to_trusted()`. All types match.
