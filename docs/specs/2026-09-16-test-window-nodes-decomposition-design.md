# `test_window_nodes.py` Decomposition Design

**Goal:** Reduce `tests/test_window_nodes.py` below 1000 lines by organizing its
existing tests into responsibility-focused case modules without changing test
meaning or production behavior.

**Stable boundary:** Keep `tests/test_window_nodes.py` as the unittest facade.
It imports the existing test classes and shared builders required by repository
references, so `python -m unittest tests.test_window_nodes` remains valid.

**Case modules:** Create `tests/window_node_cases/` with non-`test_*.py` modules
so unittest discovery does not execute cases both directly and through the
facade:

- `selector.py`: selector, dialog opener, and node presentation wiring.
- `connections.py`: connection tests, manual hosts, invites, and cluster joins.
- `switching.py`: selected-node switching, scheduler/provider mirrors, and
  resource refresh behavior.
- `discovery_pairing.py`: discovery candidates, pairing, cancellation, and
  shutdown lifecycle.
- `resources.py`: local/remote resource dialog capability and mutation gates.
- `roles.py`: enrolled-member role RPC dispatch and fail-closed behavior.

Existing `tests/support/` modules remain canonical for reusable fixtures. Keep
test-specific builders local when they encode a case group’s meaning. Preserve
all test method names, assertions, detailed explanatory docstrings, edge cases,
patch targets, and production module imports.

**Migration:** Move one complete class at a time in the listed order. Keep
shared builders in the facade only while multiple case modules use them; move a
builder with its class when it is specialized. Do not alter production code or
rewrite tests to implementation details.

**Validation:** Capture the baseline test count, run the facade after every
wave, check that no tests disappear or duplicate, and run the complete suite,
Ruff, formatting, Pyright, Mypy, and `git diff --check` at the end. Existing
repository-wide static baseline failures remain explicitly reported.
