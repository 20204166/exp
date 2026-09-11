# Page Refresh Smoothness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate the measured UI-thread freeze/hitch, flicker/double-render, slow-update, and layout-jump caused by full-list widget rebuilds on every page refresh, by switching the cluster and nodes/connections pages to incremental (diff-based) rendering that updates text in place and rebuilds only structurally-changed rows.

**Architecture:** Two presentation-only pages currently do `clear_children(body)` + rebuild all rows on every refresh (`maintenance/ui/cluster_page.py:148-166`, `maintenance/ui/nodes_connections.py:247-345`, `337-345`, `699+`). Measured on a live Tk root: `cluster_page.refresh_nodes` = 5.9ms/20 nodes, 16.4ms/50 nodes (p95 21ms); `nodes_connections.refresh_trusted` = 34.6ms/20 nodes, **83.1ms/50 nodes (p95 102ms)**. These run on the UI thread and are triggered every dashboard scan completion (`show_snapshot` → `_refresh_cluster_page`, `window.py`/`window_presentation.py:41`) and on peer attach/detach + discovery events (`window_discovery.py:499-512`). The fix retains row widgets across refreshes: text-only changes update labels in place; structural changes rebuild only that row; removed rows are destroyed; new rows are appended. Because `last_refresh` changes every scan, text updates must be in-place or the diff still rebuilds everything.

**Tech Stack:** Python 3.11+ Tkinter; tests are `unittest` under `tests/`; `tests.test_cluster_page` and `tests.test_nodes_connections_page` pin current widget structure; `tests/dump_ui.py` is the render-structure evidence harness.

---

## File Structure Map

| File | Responsibility |
|------|----------------|
| `maintenance/ui/cluster_page.py` | `_node_row` returns the row + label refs; `refresh_nodes` becomes incremental |
| `maintenance/ui/nodes_connections.py` | `_peer_row`/`_trusted_row`/manual row return row + label refs; `refresh_discovered`/`refresh_trusted`/`refresh_manual` incremental |
| `tests/test_cluster_page.py` | Update `test_real_tk_rebuilds_release_destroyed_buttons`; add retention/update tests |
| `tests/test_nodes_connections_page.py` | Add incremental-retention tests |
| `docs/plans/2026-09-11-page-refresh-smoothness.md` | This plan |

---

## Measured Baseline (evidence, do not change)

`python3 /tmp/opencode/measure_pages.py` on a live Tk root:

| Operation | 5 | 20 | 50 (median / p95) |
|---|---|---|---|
| `cluster_page.refresh_nodes` | 1.9ms | 5.9ms | 16.4 / 21.2ms |
| `nodes_connections.refresh_trusted` | 10.6ms | 34.6ms | 83.1 / 101.6ms |

After the fix, re-run the same harness and record the new numbers for unchanged-spec and text-only-change refreshes.

**After (committed `1564a6f` + `bd9e2de`, structurally-identical refreshes, median):**

| Operation | 5 | 20 | 50 |
|---|---|---|---|
| `cluster_page.refresh_nodes` | 0.16ms | 0.63ms | 1.54ms |
| `nodes_connections.refresh_trusted` | 0.20ms | 0.89ms | 1.79ms |

~10x faster cluster page (16.4→1.54ms) and ~46x faster trusted list (83.1→1.79ms) at 50 nodes. Full suite 1353 OK; `tests/dump_ui` render structure unchanged; `test_live_tk_resize` OK.

---

### Task 1: ClusterPage incremental refresh

**Files:**
- Modify: `maintenance/ui/cluster_page.py` (`_node_row`, `refresh_nodes`, `__init__`)
- Test: `tests/test_cluster_page.py`

- [ ] **Step 1: Read the current page and coordinator**

Read `maintenance/ui/cluster_page.py` `__init__` (line ~76-146), `refresh_nodes` (148-166), `_node_row` (175-296), and `maintenance/ui/action_coordinator.py` (`register`, `clear_prefix`, `bind`, `registered_ids`). Note that `_node_row` currently returns nothing and `refresh_nodes` calls `clear_prefix("cluster:node:")` then `clear_children(self._body)` and rebuilds.

- [ ] **Step 2: Write the failing retention test (TDD)**

Add to `tests/test_cluster_page.py`:

```python
    @unittest.skipUnless(DISPLAY_AVAILABLE, "Tk display unavailable")
    def test_unchanged_rows_are_retained_across_refresh(self) -> None:
        root = tk.Tk()
        coordinator = ButtonCoordinator()
        page = ClusterPage(
            root,
            callbacks=make_callbacks(),
            nodes=[_spec("dev", selectable=True)],
            button_coordinator=coordinator,
        )
        try:
            prior = coordinator._actions["cluster:node:dev:open"].widgets[0]
            page.refresh_nodes([_spec("dev", selectable=True)])
            self.assertTrue(prior.winfo_exists())
        finally:
            root.destroy()
            page.dispose()
```

Expected: FAIL (`assertTrue(prior.winfo_exists())` — the row is currently destroyed).

Also add a test that a text-only change (e.g. `last_refresh` or `status`) updates without destroying the row:

```python
    @unittest.skipUnless(DISPLAY_AVAILABLE, "Tk display unavailable")
    def test_text_only_change_updates_in_place(self) -> None:
        root = tk.Tk()
        page = ClusterPage(
            root, callbacks=make_callbacks(), nodes=[_spec("dev", selectable=True)]
        )
        try:
            row = page._rows["dev"]
            page.refresh_nodes([_spec("dev", selectable=True)])
            self.assertIs(page._rows["dev"], row)
        finally:
            root.destroy()
            page.dispose()
```

- [ ] **Step 3: Implement incremental refresh in `cluster_page.py`**

- In `__init__`, add `self._rows: dict[str, Any] = {}` and `self._empty_label: Any | None = None` before the initial `self.refresh_nodes(...)` call.
- Change `_node_row` to `return row` (the frame created at its top).
- Rewrite `refresh_nodes`:

```python
    _STRUCTURAL = ("selectable", "status", "role", "role_editable", "paused",
                   "has_active_job", "capabilities", "trust", "is_local",
                   "pairing_state", "target_state")

    def refresh_nodes(self, nodes: list[ClusterNodeSpec]) -> None:
        if self._disposed:
            return
        incoming = {spec.node_id: spec for spec in nodes}
        for node_id in [key for key in self._rows if key not in incoming]:
            self._remove_row(node_id)
        for spec in nodes:
            previous = self._nodes.get(spec.node_id)
            if spec.node_id not in self._rows:
                self._rows[spec.node_id] = self._node_row(self._body, spec)
            elif previous is not None and not self._same_row(previous, spec):
                self._remove_row(spec.node_id)
                self._rows[spec.node_id] = self._node_row(self._body, spec)
            else:
                self._update_row(spec)
        self._nodes = {spec.node_id: spec for spec in nodes}
        self._repack_in_order(nodes)
        self._update_empty_state(nodes)

    @staticmethod
    def _same_row(previous: ClusterNodeSpec, current: ClusterNodeSpec) -> bool:
        return all(
            getattr(previous, name) == getattr(current, name)
            for name in ClusterPage._STRUCTURAL
        )

    def _remove_row(self, node_id: str) -> None:
        coordinator = self._button_coordinator
        if coordinator is not None:
            coordinator.clear_prefix(f"cluster:node:{node_id}:")
        row = self._rows.pop(node_id, None)
        if row is not None:
            row.destroy()

    def _repack_in_order(self, nodes: list[ClusterNodeSpec]) -> None:
        for spec in nodes:
            row = self._rows.get(spec.node_id)
            if row is not None:
                row.pack(fill="x", pady=(0, 10))

    def _update_empty_state(self, nodes: list[ClusterNodeSpec]) -> None:
        if nodes:
            if self._empty_label is not None:
                self._empty_label.destroy()
                self._empty_label = None
        elif self._empty_label is None:
            self._empty_label = self.label_cls(
                self._body,
                text="No machines registered yet.",
                bg=self.colors["card"],
                fg=self.colors["muted_text"],
                font=self.fonts["body"],
                anchor="w",
            )
            self._empty_label.pack(anchor="w", pady=(0, 4))
```

- `_update_row(spec)`: rebuild the row's dynamic content in place. The simplest robust approach that satisfies both the text-only and structural cases: rebuild the row only when structural fields changed (handled above), and for text-only changes re-create just the row's text labels by storing them in `__init__`-time row state. To keep this plan concrete and small, have `_node_row` store the meta label as an attribute on the returned row (`row._meta_label`) and update it in `_update_row`:

```python
    def _update_row(self, spec: ClusterNodeSpec) -> None:
        row = self._rows.get(spec.node_id)
        if row is None:
            return
        meta = getattr(row, "_meta_label", None)
        if meta is not None:
            meta.config(text=self._meta_text(spec))
        name = getattr(row, "_name_label", None)
        if name is not None:
            name.config(text=spec.display_name)
```

- Extract the `meta` string construction from `_node_row` (lines ~205-221) into `_meta_text(self, spec)` and assign the meta label widget to `row._meta_label` and the name label to `row._name_label` inside `_node_row`.

- [ ] **Step 4: Run the tests**

Run: `python3 -m unittest tests.test_cluster_page -q`
Expected: PASS (the two new tests green). Update `test_real_tk_rebuilds_release_destroyed_buttons` so it no longer asserts destruction of unchanged rows — instead assert that repeated refresh of a structurally-identical spec keeps exactly one registered widget and it is the retained row's button:

```python
    @unittest.skipUnless(DISPLAY_AVAILABLE, "Tk display unavailable")
    def test_retained_buttons_stay_registered_exactly_once(self) -> None:
        root = tk.Tk()
        coordinator = ButtonCoordinator()
        page = ClusterPage(
            root,
            callbacks=make_callbacks(),
            nodes=[_spec("local", selectable=True)],
            button_coordinator=coordinator,
        )
        try:
            prior = coordinator._actions["cluster:node:local:open"].widgets[0]
            for _ in range(30):
                page.refresh_nodes([_spec("local", selectable=True)])
                self.assertTrue(prior.winfo_exists())
                widgets = coordinator._actions["cluster:node:local:open"].widgets
                self.assertEqual(len(widgets), 1)
                self.assertIs(widgets[0], prior)
            page.refresh_nodes([])
            self.assertEqual(coordinator.registered_ids(), ())
        finally:
            root.destroy()
            page.dispose()
```

Run the full page test module again; expect all green.

- [ ] **Step 5: Re-measure**

Run: `python3 /tmp/opencode/measure_pages.py`
Expected: `cluster_page.refresh_nodes` for 50 nodes drops from ~16ms to well under 2ms for structurally-identical or text-only refreshes.

- [ ] **Step 6: Commit**

```bash
git add maintenance/ui/cluster_page.py tests/test_cluster_page.py
git commit -m "perf: retain cluster page rows across refreshes and update in place"
```

---

### Task 2: NodesConnectionsPage incremental refresh

**Files:**
- Modify: `maintenance/ui/nodes_connections.py` (`refresh_discovered`, `refresh_trusted`, `refresh_manual`, `_peer_row`, `_trusted_row`, manual row, `_build_*` bodies)
- Test: `tests/test_nodes_connections_page.py`

- [ ] **Step 1: Read the current page**

Read `maintenance/ui/nodes_connections.py` `refresh_discovered` (247-257), `_peer_row` (259-319), `refresh_trusted` (337-345), `_trusted_row` (347-634), `refresh_manual` (699+), and `_build_manual_hosts_section` (636-673).

- [ ] **Step 2: Write the failing retention tests (TDD)**

Add to `tests/test_nodes_connections_page.py`:

```python
    def test_unchanged_trusted_row_is_retained(self) -> None:
        page, _parent, recorder = make_page()
        before = list(page._trusted_rows)
        page.refresh_trusted(make_trusted_specs(1))
        # Rebuild with the same spec object list (identical specs).
        page.refresh_trusted(make_trusted_specs(1))
        self.assertEqual(before, list(page._trusted_rows))
```

(Adapt to the existing test helpers in that file: confirm the fixture builders and constructor kwargs first, then mirror them exactly. `_trusted_rows` is the new per-section row dict; the plan adds `self._trusted_rows`/`self._discovered_rows`/`self._manual_rows` in `__init__`.)

Expected: FAIL — the current page destroys and rebuilds rows each refresh.

- [ ] **Step 3: Implement incremental refresh in `nodes_connections.py`**

Mirror the Task 1 approach per section:
- In `__init__`, add `self._discovered_rows`, `self._trusted_rows`, `self._manual_rows` (dicts keyed by node_id) and per-section empty-label refs.
- `_peer_row`/`_trusted_row`/manual-row builders return the row frame and store text labels (`_name_label`, `_status_label`, `_meta_label`) as attributes for in-place updates.
- `refresh_discovered`/`refresh_trusted`/`refresh_manual`: remove rows whose id is gone (clear per-node coordinator prefix `nodes:peer:{id}:`, `nodes:trusted:{id}:`, `nodes:manual:{id}:`, then `destroy`), rebuild rows whose structural fields changed, update text labels in place otherwise, repack in order, manage the empty-state label.
- Keep `clear_children` OUT of the hot path; it is no longer called on refresh.

Structural fields per section: for trusted rows, treat the presence of the permission/role/button controls (i.e. any change to `permissions`, `roles`, `role_editable`, `paused`, `selectable`, `status`, `is_manual`, `target_state`, `identity_status`) as structural; `display_name`, `hostname`, `host`, `port`, `last_refresh`-style text as text-only.

- [ ] **Step 4: Run the tests**

Run: `python3 -m unittest tests.test_nodes_connections_page -q`
Expected: PASS. Fix any test that asserted wholesale destruction (e.g. button-released-after-refresh assertions) to assert retention instead, keeping every other widget-structure assertion intact.

- [ ] **Step 5: Re-measure**

Run: `python3 /tmp/opencode/measure_pages.py`
Expected: `nodes_connections.refresh_trusted` for 50 nodes drops from ~83ms to well under 3ms for structurally-identical refreshes.

- [ ] **Step 6: Commit**

```bash
git add maintenance/ui/nodes_connections.py tests/test_nodes_connections_page.py
git commit -m "perf: retain nodes/connections page rows across refreshes and update in place"
```

---

### Task 3: Render-structure evidence + full validation

**Files:**
- `tests/dump_ui.py` (read-only harness; run it)
- `tests/test_cluster_page.py`, `tests/test_nodes_connections_page.py`, `tests/test_live_tk_resize.py`

- [ ] **Step 1: Run the render-structure harness**

Run: `python3 -m tests.dump_ui` (or the documented invocation) and confirm the emitted page structure is unchanged from the pre-fix output for a fresh build (initial build still creates the full tree; only refresh differs).

- [ ] **Step 2: Run the full suite**

Run: `python3 -m unittest discover -s tests -q` — expect all OK (~1349+ tests).

- [ ] **Step 3: Static checks**

Run: `python3 -m compileall -q maintenance tests` and `git diff --check`. Keep new lines under 88 chars.

- [ ] **Step 4: Live-Tk resize sanity**

Run: `python3 -m unittest tests.test_live_tk_resize -q` — expect PASS (skips cleanly if no display).

- [ ] **Step 5: Commit**

```bash
git add maintenance/ui/cluster_page.py maintenance/ui/nodes_connections.py tests/test_cluster_page.py tests/test_nodes_connections_page.py
git commit -m "perf: incremental page refresh retains rows and updates in place"
```

(Or fold into Task 1/2 commits if already committed.)

---

## Final Verification

- [ ] Re-run `python3 /tmp/opencode/measure_pages.py` and record the before/after table in this plan's "Measured Baseline" section.
- [ ] Full suite green (`python3 -m unittest discover -s tests -q`).
- [ ] `compileall`, `git diff --check`, `ruff check .`, `ruff format --check .`, `pyright`, `mypy --ignore-missing-imports`.
- [ ] Rebuild the wheel if source changed (`SA_VERSION_BUMP=auto ./install/build.sh`) and verify.

## Documented, out of scope for this plan

- The dashboard cards re-layout (`layout_dashboard_cards` grid_forget/grid) only on capability changes — not per-scan; left as-is.
- `queue_cluster_uploads` JSON-encodes a batch per reconcile tick — cluster-only, gated; not a per-refresh cost for single-node use.
- `sync_trusted_node_endpoint` synchronous `provider.hello()` freeze risk — separate concern; noted but not part of refresh smoothness.