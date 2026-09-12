# Cross-Platform Compatibility Audit

## Baseline

- Commit: `fa84a687447462012bfe91df881b5790d9e57c46`
- Tree: clean except pre-existing untracked `.claude/` (not touched).
- Linux regression: `python -m unittest discover -s tests -q` could not run because `python` is not on `PATH`.
- Linux regression equivalent: `python3 -m unittest discover -s tests -q` passed, `Ran 1366 tests`, `OK`.
- Compile check: `python3 -m compileall -q maintenance tests` passed.
- `ruff check .`: unavailable (`ruff` not installed).
- `ruff format --check .`: unavailable (`ruff` not installed).
- `pyright`: unavailable (`pyright` not installed).
- `mypy --ignore-missing-imports .`: unavailable (`mypy` not installed).
- The passing suite emitted expected fail-soft fixture diagnostics; it also reported environment-level `disk full` messages during tests. No test failed.

## Existing Claims Re-Verification

The capability transparency document remains consistent with the current source and
continues to state that macOS and Windows thermal execution is not natively verified.
The remote thermal plan's validation conclusion matches the current implementation:
local and remote thermal values share finite/range validation, malformed remote
samples are discarded individually, and wire metadata remains required. The current
tree already contains the shared predicate and per-sample filtering described there.

## State Vocabulary

| State | Meaning |
| --- | --- |
| VERIFIED | Evidence exists in the current environment or tests. |
| IMPLEMENTED BUT NOT NATIVE-VERIFIED | Source and fixtures exist; native host evidence is absent. |
| PARTIAL | Only part of the capability or platform path is covered. |
| UNSUPPORTED BY CURRENT PROVIDER | The current provider does not expose the capability. |
| BROKEN | Reproducible contract violation. |
| NOT APPLICABLE | The capability does not apply to the platform. |

## Phase 0 Capability Baseline

| Capability | Linux | macOS | Windows |
| --- | --- | --- | --- |
| CPU, memory, storage, network | VERIFIED | IMPLEMENTED BUT NOT NATIVE-VERIFIED | IMPLEMENTED BUT NOT NATIVE-VERIFIED |
| GPU identity and metrics | PARTIAL | IMPLEMENTED BUT NOT NATIVE-VERIFIED | IMPLEMENTED BUT NOT NATIVE-VERIFIED |
| Battery charge | VERIFIED by provider fakes and Linux run | IMPLEMENTED BUT NOT NATIVE-VERIFIED | IMPLEMENTED BUT NOT NATIVE-VERIFIED |
| Battery temperature | UNSUPPORTED BY CURRENT PROVIDER | UNSUPPORTED BY CURRENT PROVIDER | UNSUPPORTED BY CURRENT PROVIDER |
| CPU/GPU/NVMe thermals | PARTIAL: sensor availability varies | IMPLEMENTED BUT NOT NATIVE-VERIFIED | IMPLEMENTED BUT NOT NATIVE-VERIFIED |
| Process review and safe termination | VERIFIED by Linux tests | IMPLEMENTED BUT NOT NATIVE-VERIFIED | IMPLEMENTED BUT NOT NATIVE-VERIFIED |
| Downloads cleanup and Trash | VERIFIED by tests | IMPLEMENTED BUT NOT NATIVE-VERIFIED | IMPLEMENTED BUT NOT NATIVE-VERIFIED |
