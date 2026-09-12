# Cross-Platform Compatibility Audit Execution Design

## Purpose

Execute `docs/plans/2026-09-12-cross-platform-compat-audit.md` in phase order,
repairing only compatibility defects proven by repository evidence while keeping
Linux behavior as a hard regression baseline.

## Current Context

Phase 0 and Phase 1 of the audit are committed. Phase 2 produced an uncommitted
RED proof and root-cause report for the thermal capability gap. The proof showed
that repeated empty supported thermal summaries remain `NO_DATA` indefinitely.
The repository currently has no native Windows or macOS execution evidence.

## Decisions

### Phase gate correction

The intentional Phase 2 RED proof will be renamed to
`tests/thermal_capability_gap_red.py`. It remains explicitly runnable as a
unittest module and must fail before the fix, but it is excluded from
`python3 -m unittest discover -s tests` so the discovered Linux regression suite
does not contain an intentional failure. The audit plan will record this narrow
correction. Phase 3 turns the proof green and moves it into ordinary discovered
regression coverage if appropriate.

Every phase boundary requires its focused validation and a passing
`python3 -m unittest discover -s tests -q` run. A new discovered test failure is
a blocker. The exact plan command using `python -m ...` is also attempted and
reported unavailable when the executable is absent. Missing `ruff`, `pyright`,
and `mypy` are validation gaps, not passes.

### Evidence policy

Provider fakes, injected platform dispatch, and Linux execution may verify code
contracts, but they do not constitute native Windows or macOS evidence. Without
those hosts, matrix cells remain `IMPLEMENTED BUT NOT NATIVE-VERIFIED`.

### Thermal behavior

`TemperatureTelemetry` remains the owner of normalized thermal state. Add a
default `unsupported_confirm_samples` limit of 20 to `TemperaturePolicy` and a
consecutive empty-read counter to component telemetry.

- Valid samples record as `VALID` and reset the counter.
- Empty supported reads 1 through 19 remain `NO_DATA`.
- Empty supported read 20 and later become `UNSUPPORTED`.
- Provider-declared `UNSUPPORTED` remains immediate.
- Failed summaries remain `ERROR`.
- A later valid sample returns the series to `VALID`.

Card-level capability remains unchanged. No thermal values are fabricated, no
acquisition fallback is weakened, and no new polling cadence is introduced.

### Data flow and isolation

Linux psutil, macOS SMC, and Windows WMI acquisition continue to feed the shared
`ResourceSummary` and `TemperatureSample` contracts. Local and remote summaries
continue through the same `record_summary` path; no remote wire-shape change is
planned. Each `NodeContext` owns its own `TemperatureTelemetry`, so switching
nodes changes the selected state source without leaking history. Returning to a
node restores that node's bounded history.

### Phase workflow

The supplied audit phases remain in order. Phase 4 audits CPU, memory, storage,
GPU, network, battery, downloads, and Trash. Phase 5 audits process safety and
termination. Phase 6 audits config/log paths, subprocesses, encoding, and
filesystem paths. Phase 7 audits Tk rendering, resize, DPI, scrolling, focus,
contrast, and Thermals states while preserving the existing visual language.
Phase 8 audits discovery, TLS, and node identity. Phase 9 audits packaging and
Python compatibility. Phase 10 checks canonical reuse. Phase 11 checks fail-soft
performance and shutdown behavior. Phase 12 verifies thermal and node behavior.
Phase 13 records native evidence conservatively. Phase 14 updates durable
documentation and the final report.

Each production fix uses RED, confirmation of the expected failure, the smallest
implementation, focused green validation, full Linux regression, and the
required BugGuard/security review before its phase commit. Audit-only findings
do not receive speculative fixes.

## Error and Safety Boundaries

- Provider failures remain fail-soft.
- Missing sensors remain absent rather than fabricated.
- Invalid remote samples are rejected individually; valid resources and the
  authenticated session remain usable.
- Process, storage, cleanup, TLS, and remote security controls remain fail-closed.
- Protected and foreign-user processes, non-Downloads paths, symlinks, and
  non-file cleanup targets remain rejected.
- Missing native hosts and missing tools are recorded as evidence gaps.

## Scoped Artifacts

The work may update the audit matrix and thermal root-cause report, existing
BugGuard/security artifacts required by findings, tests, and implementation
files named by the audit plan. The plan itself may receive only the narrow RED
test-discovery correction and execution evidence. `.claude/` and unrelated files
remain untouched.

## Completion Criteria

- Every in-scope checkbox is addressed in order.
- Each closed phase has one phase-specific commit.
- `python3 -m unittest discover -s tests` passes after every phase.
- Static checks are run when available and otherwise listed as unavailable.
- Required edge cases are covered: slow-but-working sensors, no-sensor and
  no-battery states, remote propagation, node switching, stale-history
  isolation, and graceful fail-soft behavior.
- Windows/macOS native verification is not claimed without native evidence.
- Final status, scope, commits, remaining unsupported capabilities, and
  validation gaps are documented.

## Self-Review

- Placeholder scan: no unresolved placeholders or vague implementation requirement.
- Consistency: the RED test is explicitly excluded only until Phase 3; all phase
  boundaries otherwise require a green discovered suite.
- Scope: this is limited to executing the named audit plan and its required
  evidence, tests, fixes, and documentation.
- Ambiguity: `python3` is the available Linux interpreter; the exact `python`
  command remains separately reported when unavailable. Native platform status
  uses the existing matrix vocabulary and never treats simulation as native.
