# `test_window_nodes.py` Decomposition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decompose `tests/test_window_nodes.py` into focused case modules while preserving every test, import seam, patch target, and unittest discovery result.

**Architecture:** Keep `tests/test_window_nodes.py` as the stable facade that imports the case classes and retains genuinely shared builders. Create `tests/window_node_cases/` with modules that do not begin with `test_`, preventing unittest from discovering cases twice. Reuse existing `tests/support/` factories and keep specialized test setup with the case group that gives it meaning.

**Tech Stack:** Python 3.12, `unittest`, Tkinter fakes, existing `tests.support` factories, Ruff, Pyright, and Mypy.

---

## File Structure

- Modify: `tests/test_window_nodes.py` — facade, shared builders, and case imports.
- Create: `tests/window_node_cases/__init__.py` — package docstring only.
- Create: `tests/window_node_cases/selector.py` — `WindowNodeSelectorTests`.
- Create: `tests/window_node_cases/connections.py` — `WindowNodeConnectionTests`.
- Create: `tests/window_node_cases/switching.py` — `WindowNodeSwitchingTests`.
- Create: `tests/window_node_cases/discovery_pairing.py` — `WindowDiscoveryIntegrationTests`.
- Create: `tests/window_node_cases/resources.py` — `WindowOpenResourceNodeTests`.
- Create: `tests/window_node_cases/roles.py` — `RemoteRoleOperationTests`.
- Modify: `pyproject.toml` only if the test package must be included by configured tooling; never include tests in the production wheel.

## Hard Contracts

- Preserve all existing test class and method names.
- Preserve `python -m unittest tests.test_window_nodes` and discovery through `scripts/run_tests.sh`.
- Ensure case modules are not named `test_*.py`; the facade is the sole discovered module.
- Preserve every existing `patch()` and `patch.object()` target exactly.
- Preserve detailed explanatory docstrings, edge-case tests, fake lifecycle ordering, and assertions.
- Do not change production files or weaken tests to make extraction pass.

## Baseline and Inventory

### Task 1: Capture baseline and map ownership

**Files:** inspect `tests/test_window_nodes.py`, `tests/support/*.py`, and direct repository references.

- [ ] Run `scripts/run_tests.sh tests.test_window_nodes -v` and record the exact test count.
- [ ] Record all six class names, module-level builders, class-local helpers, imports, patch targets, and direct imports of `tests.test_window_nodes` symbols.
- [ ] Confirm existing `tests/support/models.py`, `nodes.py`, `scheduling.py`, `window.py`, and `discovery.py` are canonical before retaining or moving any builder.
- [ ] Do not edit code during this inventory step.

### Task 2: Create the case package skeleton

**Files:** create `tests/window_node_cases/__init__.py` and six empty case modules with docstrings; modify no test logic.

- [ ] Use package/module names that do not match `test_*.py`.
- [ ] Run `ruff check` and `ruff format --check` on the new package.
- [ ] Run the baseline facade test and confirm the count is unchanged.
- [ ] Commit the skeleton with `test: scaffold window node case package`.

## Incremental Class Extraction

For each task below, move the complete class body, its uniquely used imports,
and its specialized helpers into the named module. Import shared builders from
the facade during the transition, then retain only builders used by at least
two case modules in the facade. Do not alter test bodies or patch strings.

### Task 3: Extract selector tests

**Files:** modify facade; fill `selector.py`.

- [ ] Move `WindowNodeSelectorTests` unchanged and import it from the facade.
- [ ] Keep `_make_window`, `_trusted_context`, `_local_context`, and `_summary` in the facade if later groups use them.
- [ ] Run `scripts/run_tests.sh tests.test_window_nodes -v`; expected count equals baseline with no duplicate selector tests.
- [ ] Commit with `test: extract node selector cases`.

### Task 4: Extract connection tests

**Files:** modify facade; fill `connections.py`.

- [ ] Move `WindowNodeConnectionTests` unchanged, including invite, connection, and manual-host cases.
- [ ] Keep `_role_request` in the facade if switching/discovery cases use it; otherwise move it with its only consumer.
- [ ] Run the facade test and verify exact count parity.
- [ ] Commit with `test: extract node connection cases`.

### Task 5: Extract switching and discovery cases

**Files:** modify facade; fill `switching.py` and `discovery_pairing.py`.

- [ ] Move `WindowNodeSwitchingTests` and `WindowDiscoveryIntegrationTests` one class at a time.
- [ ] Keep discovery-specific helpers with discovery tests; reuse `tests.support.discovery` rather than adding a parallel fixture.
- [ ] Run the facade test after each class and verify no test is missing or duplicated.
- [ ] Commit with `test: extract node switching and discovery cases`.

### Task 6: Extract resources and remote roles

**Files:** modify facade; fill `resources.py` and `roles.py`.

- [ ] Move `WindowOpenResourceNodeTests`, `_candidate`, and `RemoteRoleOperationTests` with their class-local helpers only where ownership is clear.
- [ ] Preserve role RPC failure, stale-result, cancellation, capability, and read-only assertions exactly.
- [ ] Run `scripts/run_tests.sh tests.test_window_nodes tests.test_nodes_connections_page -v`; expected count equals baseline plus the second module’s established tests.
- [ ] Commit with `test: finish window node case extraction`.

## Final Facade and Validation

### Task 7: Clean up and verify

- [ ] Read every changed test module top to bottom and remove only obsolete facade imports/builders.
- [ ] Confirm `wc -l tests/test_window_nodes.py` is below 1000.
- [ ] Search for duplicate class definitions and verify every case module has exactly one owner.
- [ ] Run `scripts/run_tests.sh` and record the exact full-suite count.
- [ ] Run `ruff check .`, `ruff format --check .`, `pyright`, `mypy --ignore-missing-imports .`, and `git diff --check`.
- [ ] Review the final diff for deleted tests, changed patch targets, duplicate discovery, altered assertions, and unrelated edits.
- [ ] Commit final facade cleanup with `test: finalize window node test facade`.
