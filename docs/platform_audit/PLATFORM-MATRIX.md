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

## Phase 1 Platform-Assumption Inventory

The Phase 1 searches were rerun against the execution tree. Binary `__pycache__`
matches from the subprocess and cleanup searches were excluded from source
classification.

| Surface / file | Classification | Evidence and rationale |
| --- | --- | --- |
| `scanner_support/smc.py` Darwin guard | CORRECT PLATFORM ADAPTER | Apple SMC access is explicitly restricted to Darwin. |
| `preferences.py`, `components/downloads.py`, `components/node_context.py`, `scanner_support/storage.py` platform dispatch | CORRECT PLATFORM ADAPTER | Platform selection is injected or branches into existing OS-specific providers. |
| `scanner_support/dashboard.py` Linux `/proc/swaps` | CORRECT PLATFORM ADAPTER | The path is reached only for Linux swap accounting. |
| `scanner_support/dashboard.py` and `gpu.py` PowerShell flags | CORRECT PLATFORM ADAPTER | Windows-only `CREATE_NO_WINDOW` handling surrounds Windows commands. |
| `scanner_support/gpu.py` `system_profiler`/`lspci` | CORRECT PLATFORM ADAPTER | Commands are selected by macOS/Linux provider dispatch. |
| `external_commands.py` shared command runner | SAFE CROSS-PLATFORM CODE | Text/JSON command execution is centralized and accepts caller-supplied creation flags. |
| `remote_security.py`, `scanner.py`, `ui/window_discovery.py` subprocess use | NOT VERIFIED | Runtime behavior depends on host command availability; no native Windows/macOS execution evidence exists. Detailed subprocess review is scoped to Phase 6. |
| `actions.py` `send2trash` | SAFE CROSS-PLATFORM CODE | Cleanup is dependency-gated and remains constrained by the action safety policy. |
| `scanner_support/dashboard.py` sensor provider dispatch | SAFE CROSS-PLATFORM CODE | Linux, Darwin, and Windows acquisition paths fail soft; native non-Linux execution is not verified. |
| `scanner_support/storage.py` Trash provider dispatch | NOT VERIFIED | Windows `SHQueryRecycleBinW` and macOS Trash paths have fixture/source evidence but no native host run. |

No Phase 1 hit met the evidence threshold for an unsafe platform assumption. No
BugGuard candidate was opened, and no application code or tests were changed.

## Phase 4 Subsystem Audit

| Subsystem | Classification | Evidence / disposition |
| --- | --- | --- |
| CPU | PARTIAL | Core-count unavailability can be cached; reproduced as a P2 needs-more-evidence follow-up. Existing usage/frequency paths passed. |
| Memory | VERIFIED | Linux `/proc/swaps` is gated correctly; Windows/macOS use psutil aggregate swap fields. Decode-failure fallback is a P3 hardening candidate, not validated. |
| Storage / Trash | IMPLEMENTED BUT NOT NATIVE-VERIFIED | Provider branches and containment tests pass. Windows native Recycle Bin and a narrow cleanup race remain unverified. |
| GPU | VERIFIED | Identity and optional metrics remain independent; malformed injectable empty detail tuple raises, but current providers normalize it before rendering. |
| Network | VERIFIED | Added and validated macOS `utun` coverage; provider-specific VPN names remain a P2 needs-more-evidence follow-up. |
| Battery | VERIFIED | No-battery, permission-limited, and no-sensor paths remain fail-soft; Phase 3 thermal state is shared without fabricated data. |
| Downloads / cleanup | IMPLEMENTED BUT NOT NATIVE-VERIFIED | OneDrive and containment behavior are covered; permission-denied sentinel existence loop needs native Windows evidence. |

No Phase 4 production defect met the proof threshold for an in-phase fix. The
CPU, VPN, memory, Downloads, and storage observations are recorded as scoped
follow-ups rather than silently patched or promoted to validated bugs.

## Phase 6 Config, Command, and Encoding Audit

| Surface | Classification | Evidence / disposition |
| --- | --- | --- |
| Preferences and Downloads path ownership | VERIFIED | `preferences.py` owns platform-specific configuration paths; `scanner_support/paths.py` delegates Downloads resolution to `DownloadsPathResolver`. |
| Application log path | VERIFIED | `main.default_log_path` selects Linux XDG state, macOS `~/Library/Logs`, and Windows `LOCALAPPDATA`/`APPDATA` fallbacks; deterministic regression coverage added. |
| External command execution | VERIFIED | All scanner commands use the shared runner or preserve an explicit direct TLS boundary; no `shell=True` usage exists. Windows console suppression is forwarded for TLS generation. |
| Subprocess decoding | VERIFIED | Shared command execution catches `UnicodeError` and preserves fail-soft `(empty, error)` behavior; malformed JSON remains a parser error. |
| OpenSSL availability | IMPLEMENTED BUT NOT NATIVE-VERIFIED | Missing OpenSSL remains an explicit command failure at the discovery caller boundary; Windows native availability was not testable on this Linux host. |

Phase 6 fixes are committed in `0fb9518`. Focused Phase 6 coverage passed
27 tests; the full Linux suite passed 1375 tests. Native Windows and macOS
execution remains unverified.

## Phase 8 Discovery, Remote TLS, and Identity Audit

| Surface | Classification | Evidence / disposition |
| --- | --- | --- |
| Discovery lifecycle and trust boundary | VERIFIED by Linux tests | Full D7 evidence confirms locked callback mutation, lifecycle-generation gating, untrusted/non-selectable candidates, explicit read-only pairing, and no capability escalation. |
| TLS transport and certificate pinning | VERIFIED by Linux loopback tests | Full D7 confirms TLS 1.2 minimum, DER fingerprint pinning, wrong-pin rejection, and mandatory pins for trusted transport construction. |
| HMAC, freshness, replay, capability, and permission checks | VERIFIED by tests | Full D7 confirms malformed, stale, replayed, misbound, unknown, and unauthorized requests fail closed, including destructive request-ID reuse. |
| Stable peer identity | VERIFIED by tests | Stable IDs survive metadata/address changes; identity fingerprint mismatch deselects the peer. |
| Native discovery/TLS behavior | IMPLEMENTED BUT NOT NATIVE-VERIFIED | Windows/macOS execution is unavailable in this environment; Python/OpenSSL and protocol standards were checked, but native smoke evidence is still required. |

Phase 8 full D7 review is recorded at
`docs/security_reviews/SEC-20260912-002-review.md`; all four reviewer legs and
Agent 5 are complete. No Phase 8 vulnerability or app-code fix was identified.

## Phase 9 Packaging, Installers, and Python Floor

| Surface | Classification | Evidence / disposition |
| --- | --- | --- |
| `pyproject.toml` metadata and dependencies | VERIFIED by repository tests | Python floor is `>=3.10`; Darwin excludes NVIDIA-only dependency; both console entry points and package data are declared. |
| Python 3.10 source compatibility | VERIFIED by static checks | Repository Python sources compile and pass Ruff with `--target-version py310`; no 3.11+-only syntax/API pattern was found in the audited source. |
| Unix installer scripts | VERIFIED on Linux | All eight shell scripts pass `bash -n`; packaging/deployment tests pass. |
| PowerShell installer surface | IMPLEMENTED BUT NOT NATIVE-VERIFIED | Paired scripts, shared helper contracts, and prior fixes are present and covered by source/tests; no native PowerShell runtime was available. |
| Built wheel and entry points | VERIFIED by repository tests | Package structure, wheel members, metadata, dependencies, version, and both console scripts pass deployment validation. |

Phase 9 found no packaging defect and made no application or installer-code
changes. Native Windows PowerShell execution and clean-install verification on
Python 3.10/3.11 remain required evidence for a future native smoke run.

## Phase 10 Canonical Reuse Audit

The collective Phases 3–9 reuse audit found no new duplicated mechanism that
should be consolidated. Generic subprocess execution remains owned by
`maintenance/external_commands.py`; process ancestry safety remains owned by
`maintenance/components/process_safety.py`; thermal state transitions remain
owned by `maintenance/components/temperature.py`; platform acquisition stays
under `maintenance/scanner_support/`. The separate certificate-generation
subprocess is intentionally retained because it owns TLS material lifecycle
and secret-file permissions. No Phase 10 code change was warranted.

## Phase 11 Fail-Soft, Performance, and Shutdown Audit

The Phases 3–9 diff introduced no new worker thread, timer loop, render-path
subprocess, or uncached acquisition cadence. Thermal absence confirmation uses
the existing telemetry update path and bounded per-component state. The only
subprocess change is the Windows `CREATE_NO_WINDOW` flag on an existing TLS
material command, so no performance benchmark was warranted. Existing tests
cover coordinator cancellation/shutdown, discovery teardown, stale callbacks
after close, and window finalization. No Phase 11 code change was required.

## Phase 12 Behavior Regression Tests

The permanent test `tests/test_thermal_node_isolation.py` proves that the
selection path renders each node's own telemetry history. Its false-positive
check was executed by temporarily forcing the renderer to use the local
context; the test failed on the remote-history assertion, then the production
function was restored. Focused thermal and isolation coverage passed `23/23`.
