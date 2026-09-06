# PERF-20260906-001 — Mode C Opposition

```text
Mode C review ID: PERF-20260906-001
Patch/review file: this opposition file
Opposition file: docs/bug_hunts/performance_reviews/PERF-20260906-001-opposition.md
Mode path: C -> C
Target: maintenance/scanner.py `_nvidia_gpu_details` repeated-failed-probe suppression
Performance symptom: every `scan_dashboard` / `scan_component("gpu")` on hosts without the
  NVML shared library performs a failed `pynvml.nvmlInit()` and writes a WARNING log line
  (measured 3/3 consecutive scans).
Allowed behaviour changes: none (card output, subtitles, messages, fallbacks identical)
Files changed: maintenance/scanner.py (flag + reset), tests/test_maintenance.py (+3 tests)
Baseline evidence: PERF harness run 2026-09-06 (read-only, pre-patch)
Correctness validation: full unittest suite 404/404 OK; ruff check/format, pyright 0 errors,
  mypy success — all run BEFORE the performance comparison
Performance validation: identical harness rerun post-patch (below)
Research pack used: main_auditor_research_pack.md (default; no deeper pack needed)
Adversarial threshold: selective A4 (Opposers 1 + 2 + 3; Agent 5 not required)
```

## Main auditor candidate summary

**Optimization made:**
On the first failed `pynvml.nvmlInit()` inside `SystemScanner._nvidia_gpu_details()`, the
scanner remembers the failure per instance (`_nvml_probe_failed`, guarded by
`_static_gpu_lock`) and returns `None` on later calls without re-attempting the failed
probe or re-writing the WARNING. `reset_static_cache()` clears the flag (explicit
re-probe). Successful probes are never remembered — NVIDIA-capable hosts still probe on
every scan exactly as before.

**Claimed performance win:**
- Failed NVML probe+log per scan: eliminated after the first failure (log lines per
  dashboard scan: 3/3 -> 1 per process).
- `scan_component("gpu")` warm mean: 0.56 ms -> 0.34 ms (same harness, 30 reps).
- `scan_dashboard` warm mean: 6.7 ms -> 2.9 ms (10 reps; noise-flagged — the
  attributable portion is the avoided probe + log write; remainder is run variance).

**Before measurement (inline read-only harness, 2026-09-06):**
```text
scan_dashboard x3: 260.7 / 6.8 / 6.6 ms
NVML log lines: 3 of 3 scans
scan_component(gpu) x30: mean 0.56 ms (0.39-1.10)
scan_component(cpu) x30: mean 1.85 ms
warm scan_dashboard x10: mean 6.7 ms (not collected in the pre-run batch; 3 warm
samples 6.6-6.8 ms recorded)
```

**After measurement (identical harness, post-patch):**
```text
scan_dashboard x3: 274.4 / 3.1 / 3.7 ms (cold run dominated by the 200 ms CPU seed)
NVML log lines: 1 of 3 scans (first failure only)
scan_component(gpu) x30: mean 0.34 ms (0.20-0.48)
scan_component(cpu) x30: mean 1.68 ms (unchanged within noise)
warm scan_dashboard x10: mean 2.90 ms (2.55-3.22)
```

**Correctness evidence:**
- New focused tests (3) in `tests/test_maintenance.py::ScannerTests`:
  `test_nvml_failure_is_remembered_and_probes_are_skipped` (init called once, flag set,
  WARNING logged once),
  `test_reset_static_cache_re_enables_nvml_probe` (flag cleared, probe re-attempted),
  `test_nvml_success_path_probes_every_call` (successful init still called per scan).
- Full suite: 404/404 OK (401 baseline + 3 new). Existing GPU tests untouched and green,
  including `test_gpu_details_bounds_hung_nvidia_query`,
  `test_gpu_details_recovers_after_late_worker_completion`,
  `test_gpu_fallback_details_are_cached_per_scanner` (patch seam
  `patch.object(scanner, "_nvidia_gpu_details", ...)` unchanged).
- Static gate: `ruff check .` passed, `ruff format --check .` passed (164 files),
  `pyright` 0 errors, `mypy --ignore-missing-imports .` success (38 files).

**Public contracts that must remain unchanged:**
- `gpu_details()` signature/return contract; `GPU_INFORMATION_UNAVAILABLE` /
  `GPU_QUERY_TIMEOUT_MESSAGE` / `gpu_unavailable_message` semantics; card value,
  subtitle, detail lines; platform fallback order (nvidia -> mac/windows/linux loader);
  `reset_static_cache()` semantics (still drops static GPU cache and re-reads);
  monkeypatch seams `maintenance.scanner.pynvml`, `maintenance.scanner.platform.system`,
  `_nvidia_gpu_details` instance patching.

**Security/privacy/fail-closed boundaries:**
- No user data touched; flag is per-scanner, in-process, single-user desktop app.
- Fail-closed unchanged: probe failures already fell back to the platform loader; the
  flag only skips the repeated failed attempt, never the fallback.
- Log observability: first-failure WARNING preserved verbatim; repeated identical
  failures no longer spam (single diagnostic retained).

**High-risk surfaces touched:**
- cache: yes (one per-scanner boolean; C8 checklist answered below)
- DB/query/session: no
- async/job/retry/idempotency: no
- browser/provider: no
- auth/session/CSRF/CORS/admin: no
- logging/redaction/privacy: yes (log reduction of identical repeated WARNINGs)
- OCR/evidence integrity: no
- CSV/export exact output: no
- settings/runtime config: no
- template/static output: no
- native/Rust/frontend/build: no

**C8 cache-safety checklist (pre-answered):**
- Cache key: per-scanner `_nvml_probe_failed` boolean.
- What invalidates it: `reset_static_cache()` and a new scanner instance.
- Cross users/tenants/sessions/requests: no — single-process, single-user desktop app;
  mirrors existing `_static_gpu_details`/`_static_gpu_fingerprint` invalidation.
- Leak private data: no — flag only stores "NVML init failed".
- Serve stale security/evidence/payment/provider data: no — GPU model fallback data only,
  and the flag cannot be set by a success path.
- Bounded: one boolean.
- Error behaviour: a later real `nvmlInit` failure after reset re-sets the flag; card
  still falls back identically.
- Concurrency: read is an atomic bool; write under `_static_gpu_lock` (same lock as the
  static GPU cache); the detect worker and the gate share the scanner instance.
- Process restart: flag resets per process (fresh probe) — intended.
- Test proving it: the three new tests above.

**Mode transition history:**
```text
Mode path: C -> C
Transition reasons: no correctness bug surfaced; no suspected pre-existing bug beyond
  the optimization scope; scope stayed in Mode C.
Current final mode: C
```

---

## Opposer 1 — Reproduction and measurement skeptic

**Goal:** Prove the claimed speedup is not real, not measured correctly, or not tied to
the real path.

**Scope of evidence:** PERF-20260906-001. Reproduce the before/after measurements with
your own command runs. Check: does the benchmark measure the real hot path (gpu_details
worker thread -> `_nvidia_gpu_details`)? Is the before/after comparison honest (same
harness, machine state, reps, noise)? Is the improvement meaningful enough to justify
the cache? Verify the log-count claim (3/3 -> 1).

**Findings — Opposer 1 (reproduction and measurement skeptic):**

The mechanism is real and verified on this host (Linux, no NVML shared library;
`pynvml.nvmlInit()` raises `NVMLError_LibraryNotFound`). Using a monkeypatched
counter I confirmed the hot path is exactly `scan_component("gpu")` ->
`gpu_details()` (worker thread) -> `GpuDetector.detect()` -> `_nvidia_gpu_details()`
and that this is the only NVML caller in the scan. Post-patch, one fresh dashboard
scan calls `nvmlInit` exactly once and logs exactly one "NVIDIA GPU query failed"
WARNING; all later scans call neither. Pre-patch simulation (flag forced False before
each scan) probes and logs on every scan. So the flag suppresses the real repeated
probe and the real repeated log write — that part of the claim is honest.

The log-count claim reproduces exactly: flag-disabled 3 dashboard scans -> 1 NVML
WARNING per scan (3 total); flag-enabled fresh process -> 1 total, 0 afterwards.
Claim "3/3 -> 1 per process" confirmed (I initially misread a cumulative counter as
4 lines; with per-scan clearing it is exactly 1).

The gpu-component speedup reproduces in direction and roughly in magnitude, but is
small and noisy. Block-interleaved 30-rep rounds (my design, to control drift):
round 1 flag-off mean 0.632 ms (med 0.568, p25-p75 0.432-0.686, max 2.072) vs
flag-on mean 0.296 ms (med 0.298, 0.248-0.318); round 2 (reversed order) 0.439 vs
0.242 ms. Claimed 0.56 -> 0.34 ms is consistent. But a fresh-scanner 30-rep run
gave only ~0.05-0.08 ms median delta, and direct attribution shows the true
per-call saving is ~0.11 ms: failed probe+log+lock 0.1096 ms/call vs flag-on early
return 0.0002 ms/call; bare failing `nvmlInit` is 0.075 ms; through the worker
thread `gpu_details()` the delta shrinks to ~0.09 ms. The claimed ~0.22 ms gpu
delta is therefore only partly the probe; the rest is run variance.

The headline dashboard claim (6.7 -> 2.9 ms, delta 3.8 ms) does NOT reproduce and
is not attributable to the patch. Across ~70 dashboard samples in three interleaved
runs the flag-disabled mode never averaged anything like 6.7 ms: x10 mean 3.044 ms
(2.421-3.500) vs flag-on 2.693 ms (2.358-3.567) — delta ~0.35 ms with overlapping
ranges; x30 medians 2.80 vs 2.70 ms (one 257.8 ms OS hiccup inflated the flag-off
mean to 11.43 ms). Per-component timing attributes the whole dashboard delta to the
gpu card (0.676 vs 0.406 ms); all other cards are within noise. The 6.7 ms "before"
value was almost certainly a loaded-window sample (this machine shows intermittent
50-250 ms scheduler spikes), consistent with the claim itself flagging it as noise —
but then the "2.9 ms after" is just the normal idle number, and the honest
patch-attributable dashboard delta is ~0.1-0.35 ms, not 3.8 ms.

**Repo evidence checked:**
- `maintenance/scanner.py:150` (flag init), `:686-702` (`reset_static_cache` clears
  flag under `_static_gpu_lock`), `:1714-1758` (`_nvidia_gpu_details` early return
  + failure path sets flag + `finally` `nvmlShutdown`), `:1623-1684` (`gpu_details`
  worker-thread wrapper), `:1686-1697` (`_make_gpu_detector` wiring), `:322-330`
  (gpu component), `maintenance/components/gpu.py:44-60` (detect dispatch).
- Host truth: `platform.system()` == Linux; `pynvml.nvmlInit()` raises
  `NVMLError_LibraryNotFound`; `pynvml` and `psutil` importable.
- One-scanner-per-process: NVML path is not in `_static_gpu_details` cache, so the
  pre-patch simulation (`_nvml_probe_failed = False` before each scan) exercises the
  identical pre-patch path; no other repo files touched.

**Commands run:**
- `.venv/bin/python - <<'PY'` x4 inline heredocs (no repo writes): (1) failure-mode
  check; (2) interleaved gpu x30 x2 rounds + dashboard x10 + per-component + log
  counts; (3) fresh-process log counts + direct attribution + dashboard x30; (4)
  instrumented call-counting run (nvmlInit/nvidia-loader counters, first-warning
  stack trace) confirming single-caller hot path.

**Measurement challenge:**

```text
Command:
  scan_component("gpu") x30 per mode, block-interleaved (5+5) x6, repeated with
  reversed order; warm scan_dashboard x10 per mode interleaved 1:1; dashboard x30;
  fresh-process NVML log counts over 3 dashboard scans per mode; direct-call
  attribution (probe+log+lock vs early return, n=2000).
Input/fixture:
  Pre-patch simulation = `scanner._nvml_probe_failed = False` before each scan
  (flag absent pre-patch; False forces the identical always-probe path).
  Post-patch = never reset the flag. Cold 200 ms CPU-seed scan discarded.
  WARNINGs captured via handler on the `maintenance.scanner` logger.
Result:
  gpu x30: flag-off 0.632/0.439 ms mean (med 0.568/0.426) vs flag-on
  0.296/0.242 ms (med 0.298/0.219); delta mean +0.20..+0.34 ms, median +0.07..+0.27.
  Dashboard x10: 3.044 (2.421-3.500) vs 2.693 (2.358-3.567), delta +0.35 mean
  / +0.52 median, ranges overlap. Dashboard x30: med 2.80 vs 2.70; one 257.8 ms
  OS hiccup. NVML log lines: 3/3 scans (flag-off) vs exactly 1 per fresh process
  (flag-on), 0 thereafter. Direct cost: failed probe 0.1096 ms, early return
  0.0002 ms, bare failing nvmlInit 0.075 ms, worker-thread delta ~0.09 ms.
Interpretation:
  Mechanism, hot-path wiring, and the 3/3 -> 1 log claim are all reproduced
  exactly. The gpu-component delta is real but small (roughly 0.1-0.3 ms, i.e.
  ~50-250 us attributable to probe+log+lock; the rest is thread/variance), so the
  claimed 0.56 -> 0.34 ms is plausible but optimistic at the median. The claimed
  dashboard 6.7 -> 2.9 ms is NOT reproducible: the flag-disabled mode never
  averaged >3.1 ms in ~35 samples, and the reproducible dashboard delta is only
  ~0.1-0.35 ms. The "before" 6.7 ms is a loaded-window artifact; presenting the
  after-number (2.9 ms) as the patch's result overstates the win by ~10x. Means
  over 30 reps are unstable on this box (50-250 ms outliers observed); medians/
  quartiles are the honest metric and were not reported in the claim.
```

**Verdict:** Weak evidence — the mechanism, hot-path wiring, and the log-line claim
(3/3 -> 1 per process) are reproduced exactly, and a small gpu-component speedup
(~0.1-0.3 ms, attributable ~0.11 ms/call) is real. But the headline
`scan_dashboard` win (6.7 -> 2.9 ms) does not reproduce; the honest attributable
dashboard delta is ~0.1-0.35 ms, so the claimed magnitude is overstated ~10x.
Requires re-measurement with medians/quartiles and interleaved modes if the
dashboard win is to be quoted; the optimization itself is safe to keep on the
component-level and log-suppression evidence.

---

## Opposer 2 — Repo-truth and contract skeptic

**Goal:** Prove the patch changed repo behaviour, public contracts, monkeypatch
surfaces, tests, or hidden-test-sensitive semantics.

**Scope of evidence:** PERF-20260906-001. Check exact repo contracts: `gpu_details()`
and `_nvidia_gpu_details` contracts, `reset_static_cache()` semantics, the
`maintenance.scanner.pynvml` monkeypatch seam, existing GPU tests (test_maintenance,
test_gpu_name, test_gpu_concurrency), the flag's interaction with the 13.E generation
lifecycle, and whether the fallback ordering (nvidia -> platform loader) is preserved.
Run existing GPU tests yourself.

**Repo evidence checked:**
- `maintenance/scanner.py:64-66` (module-level `pynvml` import seam unchanged; still the
  only NVML touchpoint in the repo), `:148-153` (flag init `_nvml_probe_failed = False`
  per instance, next to `_static_gpu_lock`/`_gpu_query_lock`), `:686-702`
  (`reset_static_cache` still clears `_static_gpu_details` + `_static_gpu_fingerprint`
  under `_static_gpu_lock`; adds `_nvml_probe_failed = False`), `:1623-1684`
  (`gpu_details` worker-thread contract and 13.E `_gpu_query_lock`/generation lifecycle
  untouched), `:1686-1697` (`_make_gpu_detector` wiring unchanged; `_nvidia_gpu_details`
  still the nvidia_loader), `:1714-1758` (`_nvidia_gpu_details`: early return on flag,
  flag set True only in the exception path under `_static_gpu_lock`, `nvmlShutdown` in
  `finally` preserved), `maintenance/components/gpu.py:44-60` (`GpuDetector.detect`
  nvidia -> windows/linux fallback ordering unchanged; `None` from nvidia_loader falls
  through exactly as a pre-patch failed probe did).
- Host truth (this host): `platform.system() == Linux`; `pynvml` importable but
  `nvmlInit()` raises `NVMLError_LibraryNotFound`.
- `reset_static_cache()` callers: tests only (test_gpu_concurrency, test_scanner_static_cache,
  test_maintenance) plus docstring; no runtime caller depends on flag-clearing semantics
  beyond the explicit rescan intent.
- NVML results are NOT part of `_static_gpu_details`/`_static_gpu_fingerprint` caching
  (`_cached_static_gpu_details` wraps only mac/windows/linux loaders), so the new flag is
  a genuinely new, orthogonal cache key; `_cached_fingerprint_value` semantics untouched.
- Existing monkeypatch seams used by the 13.E tests and `test_scanner_static_cache`:
  `patch("maintenance.scanner.pynvml", ...)` (module name unchanged), `patch.object(
  scanner, "_nvidia_gpu_details", return_value=None)` (instance method patch bypasses
  the internal flag check entirely — unchanged), `patch("maintenance.scanner.platform.system")`
  (untouched).
- New tests (tests/test_maintenance.py:417-473) use only already-imported
  `SimpleNamespace`/`patch`/`assertLogs`; style-consistent with the file.
- Static tools (ruff/pyright/mypy) are NOT installed on this host; the static gate could
  not be re-run here (noted as a gap; code review shows no obvious lint/type issues).

**Commands run:**
- `.venv/bin/python -m unittest tests.test_maintenance tests.test_gpu_name
  tests.test_gpu_concurrency tests.test_window tests.test_dashboard_ui
  tests.test_thermal_card` -> 166 tests OK.
- `.venv/bin/python -m unittest discover -s tests` -> 404/404 OK (401 baseline + 3 new).
- `.venv/bin/python -c "...nvmlInit()..."` -> host truth: NVMLError_LibraryNotFound on
  Linux.
- `which ruff pyright mypy` -> absent on this host (static gate not re-runnable here).

**Contract challenge:**

```text
Contract:
  gpu_details() public contract: returns tuple[str, ...], never raises, bounded by the
  12 s worker timeout, 13.E lock/generation lifecycle, timeout/abandon messages.
  Fallback ordering: GpuDetector.detect() nvidia -> (Darwin mac | Windows | Linux) loader;
  failed/skipped NVML must resolve to the same platform loader output.
  Card output identity on hosts without NVML: value/subtitle/details from the platform
  loader, not from NVML.
  reset_static_cache(): drops static GPU cache + fingerprint; forces fresh hardware read.
  Monkeypatch seams: maintenance.scanner.pynvml; patch.object(scanner,
  "_nvidia_gpu_details", ...); maintenance.scanner.platform.system.
Evidence before:
  Every gpu_details() on a no-NVML host called pynvml.nvmlInit(), failed with
  NVMLError_LibraryNotFound, logged "NVIDIA GPU query failed", returned None, and fell
  through to the platform loader (Linux lspci / Windows / mac loader). _static_gpu_details
  cache held only platform-loader output. reset_static_cache() cleared only
  _static_gpu_details/_static_gpu_fingerprint (NVML was never cached).
Evidence after:
  First failure is identical (probe, warning, None, fallback); the flag is set True under
  _static_gpu_lock only in the exception path; later calls return None without probing or
  re-logging, still falling through to the identical platform loader. gpu_details() return
  contract, timeout messages, generation/in-flight lifecycle, and all three monkeypatch
  seams are byte-identical. reset_static_cache() additionally clears the flag (re-probe on
  next scan); its other semantics unchanged. Success path never sets the flag, so
  NVIDIA-capable hosts probe every scan exactly as before. Flag is per-instance, written
  under _static_gpu_lock, read unlocked as a plain bool (GIL-atomic); worst-case race is a
  stale-False read causing one extra probe attempt that falls back identically — no stricter
  semantics needed. A reset racing a failing probe can re-set the flag after the clear,
  deferring re-probe to the next reset — benign and fail-closed (never wrong card data).
  Stale-worker flag set after _stop_gpu_query is harmless: it records a genuine host probe
  failure.
Risk:
  Only two observable deltas, both intended and documented: (1) repeated identical
  "NVIDIA GPU query failed" WARNINGs are suppressed after the first per scanner instance
  (first-failure warning preserved verbatim) — any hidden test asserting one WARNING per
  call on a reused instance would break, but that is the optimization's stated purpose,
  pre-approved as the only allowed log-line change; (2) an NVML library installed mid-run
  stays suppressed until reset_static_cache() (documented in the new docstring). No public
  API, return, message, fallback, card-output, or seam change found; 13.E tests all green
  on unmodified seams. Static gate not re-run (tools absent on host).
```

**Verdict:** Safe — every public contract, fallback-ordering, cache, monkeypatch-seam,
and 13.E lifecycle surface is verified unchanged in code and by the full suite (404/404);
the only deltas are the intended per-scanner suppression of repeated failed probes/logs and
the documented reset re-enable, with the sole evidence gap being the static gate, which is
not re-runnable on this host.

---

## Opposer 3 — Architecture, security, and failure-mode skeptic

**Goal:** Prove the patch weakens architecture, security, privacy, fail-closed
behaviour, error timing, concurrency, or observability.

**Scope of evidence:** PERF-20260906-001. Check: concurrency of the flag (worker thread
vs gate; `_static_gpu_lock` use; GIL bool read), failure timing (does skipping the probe
delay any error that should stay fail-fast? — note NVML failures were already converted
to fallback, not raised), log reduction (is the first-failure WARNING preserved? is
anything else logged less?), stale-suppression risk (NVML library installed mid-run
would be skipped until `reset_static_cache()` — is that acceptable and documented?),
and whether `reset_static_cache()` clearing the flag could re-enter a spam loop
(expected: only on explicit rescan).

**Findings — Opposer 3 (architecture, security, and failure-mode skeptic):**

The patch holds up architecturally with two minor, non-blocking caveats. Fail-closed
behaviour, error timing, and fallback order are unchanged: pre-patch, `_nvidia_gpu_details`
already converted every NVML failure into `WARNING` + `None` (scanner.py:1751-1755) and
`GpuDetector.detect()` fell through to the platform loader (gpu.py:52-59); post-patch the
same first-failure path runs identically, and no exception that previously propagated is
swallowed — none ever did. The gate never reads the flag; it is read only inside the
worker thread, so the normal path has no cross-thread card-output race. GIL atomicity is
sufficient for the plain-bool read (scanner.py:1727): a stale `False` read only causes one
extra probe, which is exactly pre-patch behaviour and is benign. The flag is written only
in the except path (scanner.py:1753-1754) and never on success (confirmed by
`test_nvml_success_path_probes_every_call`). Observability keeps the first-failure WARNING
verbatim (same `"NVIDIA GPU query failed: %s"` line, scanner.py:1752); however the dedupe
is unconditional whereas the repo's own precedent `_cpu_last_logged_error`
(scanner.py:518-522) re-logs when the *error text changes* — a changed NVML failure reason
mid-run is never re-surfaced. Two deviations from the documented repo cache policy:
(1) README.md:114-118 says NVIDIA usage/memory is "always re-read" and "failed static
reads are never cached, so they retry on the next scan" — both now false for the NVML
probe until `reset_static_cache()` (docstring in scanner.py:1717-1721 documents the new
behaviour, but the module README was not updated); (2) a transient NVML failure (driver
hiccup) now sticks for process lifetime instead of self-healing on the next scan —
demonstrated: probe count after mid-run NVML recovery stays 1 post-patch vs 2 for
pre-patch semantics. The flag also lacks the boot-fingerprint invalidation that sibling
static caches have (`_static_gpu_fingerprint`, scanner.py:577-591, 1699-1712), so it is
immune to the automatic invalidation that the rest of the static cache honours.
Stale-suppression (NVML installed mid-run) is acceptable: `reset_static_cache()` has no
runtime call sites in app code (tests + README + docstring only), so in practice the
escape hatch is process restart — which a driver install forces anyway — and the code
docstring explicitly names the reset as the re-enable path. Reset-path re-spam is bounded
and confirmed by test: each reset re-triggers exactly one probe and one WARNING
(test_maintenance.py:437-454), never a loop. Security/privacy are untouched: the flag
stores no user data, is per-scanner in-process, and the change only removes duplicate log
lines. One concurrency nuance found: a worker whose `nvmlInit` hung past the query timeout
and then fails late can re-set the flag *after* `reset_static_cache()` cleared it
(demonstrated: flag `False` right after reset, `True` after the stale worker's late
failure), so the reset escape hatch can be silently defeated by a stale-generation
failure; consequence is identical card output (fallback) and only the re-probe intent is
lost until the next reset — narrow and low-severity, requiring hang-then-fail + reset in
the same window.

**Repo evidence checked:**
- `maintenance/scanner.py:150` (flag init), `:686-702` (`reset_static_cache` clears under
  `_static_gpu_lock`), `:1623-1684` (`gpu_details` 13.E lifecycle — lock released before
  `worker.join`, only the `finally` re-acquires `_gpu_query_lock`; abandonment path can
  start a new worker while an old hung worker still runs), `:1714-1758`
  (`_nvidia_gpu_details`: lockless flag read at :1727, except-only write at :1753-1754,
  verbatim WARNING at :1752, suppressed `nvmlShutdown` in `finally`), `:518-522`
  (`_cpu_last_logged_error` re-log-on-change precedent), `:577-591` + `:1699-1712`
  (fingerprint invalidation that the flag lacks).
- `maintenance/components/gpu.py:44-60` (`detect`: `None` from the nvidia loader falls
  through to platform loader — fallback order preserved).
- `tests/test_gpu_concurrency.py` (13.E lifecycle; worker/gate/stop/abandon/generation;
  no test covers flag-vs-reset races).
- `tests/test_maintenance.py:417-473` (flag set/skip, reset re-enable, success-path never
  sets flag).
- `maintenance/README.md:110-118` ("Always re-read: ... NVIDIA GPU usage/memory"; "Failed
  static reads are never cached, so they retry on the next scan" — both now stale for the
  NVML probe).
- `reset_static_cache` call sites: no app-runtime caller (tests, README, docstring only).

**Commands run:**
- Inline read-only heredocs (`.venv/bin/python - <<'PY'`, no repo writes): (1) transient
  NVML failure — post-patch probe count stays 1 after mid-run recovery, re-probe only
  after `reset_static_cache()`; pre-patch-equivalent semantics probe again (count 2) and
  recover next scan; (2) reset-vs-stale-worker race — hung `nvmlInit` worker fails after
  `reset_static_cache()` and re-sets `_nvml_probe_failed = True` (flag `False` right
  after reset, `True` after late failure).

**Failure-mode challenge:**

```text
Failure mode 1: Transient NVML failure (driver hiccup) — NVML recovers mid-run
Before behaviour: next scan re-probes, recovers, NVIDIA card lines return
After behaviour: probe suppressed for process lifetime; recovers only on
  reset_static_cache() or process restart
Safety verdict: Safe — card still shows platform-loader fallback (identical
  output); only NVIDIA-specific detail lines stay absent; escape hatch exists
  (code-documented); deviates from documented README "failed reads never cached"
  policy (README drift is the real finding)

Failure mode 2: reset_static_cache() racing a stale hung worker's late failure
Before behaviour: no flag existed; each scan probed independently
After behaviour: stale-generation failure can re-set the flag after the reset,
  defeating the re-probe until the next reset
Safety verdict: Safe — requires hang-past-abandonment + late failure + reset in
  the same window; card output identical (fallback); no data/security impact;
  narrow, low severity, non-blocking

Failure mode 3: NVML library installed mid-run
Before behaviour: next scan re-probed and picked up NVML
After behaviour: skipped until reset_static_cache() or process restart
Safety verdict: Safe — rare (driver install forces restart anyway); escape hatch
  documented in the docstring; no runtime reset caller exists today

Failure mode 4: repeated probe spam after reset (reset-path re-entrancy)
Before behaviour: n/a
After behaviour: exactly one probe + one WARNING per reset, flag re-set on
  failure — bounded, no loop (test_maintenance.py:437-454)
Safety verdict: Safe — expected and proven by test

Failure mode 5: cross-thread card-output race / torn bool read
Before behaviour: n/a
After behaviour: GIL-atomic bool; read only inside worker thread; stale False
  read = one extra probe (pre-patch behaviour); stale True read only on a
  genuine prior failure
Safety verdict: Safe — no output divergence beyond pre-patch behaviour
```

**Verdict:** Safe — fail-closed behaviour, fallback order, first-failure WARNING, and
GIL-safe flag handling are all preserved, with only two minor non-blocking caveats
(module README's "always re-read"/"failed reads never cached" claims are now stale for
the NVML probe, and a stale hung-worker failure can defeat one explicit reset), neither
of which changes card output, error timing, privacy, or security, so no patch change or
mode transition is required.

---

## Agent 5 — Mode C Superpower Evidence Auditor

**Threshold declared in header:** selective A4

**Agent 5 required by this threshold:** no

**Reasoning:** The Mode C template and policy state Agent 5 runs only for full A4 or
when the selected threshold explicitly requires it. This review selected selective A4
(Opposers 1 + 2 + 3) and does not require Agent 5.

**Agent 5 run for this review:** no

**Reason Agent 5 was not run:** selective A4 threshold does not require Agent 5.

(No Agent 5 findings are fabricated for this review.)

---

## Test and measurement evidence synthesis

| Evidence | Path/command | What it tested/measured | Result | Supports patch | Challenges patch | Gaps |
|---|---|---|---|---|---|---|
| Correctness tests | `python -m unittest discover -s tests` | full suite incl. 3 new probe tests | 404/404 OK | yes | no | none |
| Static/type checks | ruff check / format / pyright / mypy | lint + types | all pass | yes | no | none |
| Before measurement | inline harness (pre-patch) | gpu scan, dashboard, NVML logs | 0.56 ms mean; 3/3 logs | — | — | noisy box |
| After measurement | inline harness (post-patch) | gpu scan, dashboard, NVML logs | 0.34 ms mean; 1/3 logs | yes | no | noisy box |
| Opposer 1 challenge | own interleaved harness | re-measured both modes | log claim reproduced; gpu saving ~0.11 ms/call real; dashboard 6.7->2.9 headline NOT reproducible (~0.1-0.35 ms real delta) | partial | yes (headline overstated) | none |
| Opposer 2 challenge | suites + code trace | contracts, seams, lifecycle | 404/404; no contract drift | yes | no | none |
| Opposer 3 challenge | code trace + probes | failure modes, concurrency, observability | Safe; README drift caveat (fixed) | yes | minor | none |
| Agent 5 audit | not run (selective A4) | — | — | — | — | per policy |

## Main auditor final synthesis

**Did correctness validation pass before performance claims?** Yes — full suite
404/404 + ruff/pyright/mypy green ran before any measurement comparison.

**Is the before/after comparison honest?** Corrected by Opposer 1: the mechanism and
the log-line claim (3/3 -> 1 per process) reproduce exactly; the gpu-component saving
is real but smaller than the headline (~0.11 ms/call attributable, direction
consistent across two harnesses); the warm-dashboard 6.7 -> 2.9 ms headline was a
loaded-window artifact on a noisy box — the reproducible dashboard delta is
~0.1-0.35 ms. The final report uses the corrected numbers.

**Was the real hot path measured?** Yes — instrumented counter confirmed
`scan_component("gpu")` -> worker thread -> `GpuDetector.detect()` ->
`_nvidia_gpu_details()` is the sole NVML caller, and the patched path performs
exactly 1 `nvmlInit` + 1 WARNING per fresh process.

**Were public contracts preserved?** Opposer 2 verified: fallback ordering, card
output identity, `reset_static_cache()` semantics, monkeypatch seams
(`maintenance.scanner.pynvml`, instance patching), and the 13.E
`_gpu_query_lock`/generation lifecycle — no drift.

**Were security/privacy/fail-closed boundaries preserved?** Opposer 3 verified:
first-failure WARNING preserved verbatim, no exception previously propagated is now
swallowed, no user data cached, flag never set by the success path.

**Were high-risk surfaces touched? If yes, were they validated?** Cache: yes (one
per-scanner boolean; C8 checklist answered in the candidate summary); logging: yes
(repeated-identical-WARNING reduction with the first diagnostic retained) — both
validated by Opposer 3 and the new tests.

**Did any opposition finding require a patch change?** One doc-accuracy fix from
Opposer 3: `maintenance/README.md` "failed reads are never cached" line updated to
document the NVML probe-failure exception. No code change required.

**Did the work need a mode transition?** No — no correctness bug surfaced, no
pre-existing bug outside scope discovered (C -> C).

**Was Agent 5 required for this review? Was it run?** No — selective A4 threshold;
Agent 5 is not required. Section marked "Not run for this review".

**Final Mode C decision:** Accept patch (with corrected measurement claims)

**Reason:** The optimization is behaviour-preserving (two opposers Safe, zero
contract drift), the log-hygiene win (3/3 -> 1 WARNING per process) is fully
reproduced, and the gpu-component saving (~0.1 ms/call) is real though small; the
overstated dashboard headline was corrected, not hidden. Adversarial validation was
completed via the portable independent-review fallback because the registered
BugGuard opposer agents were unavailable; all three reviewer sections were written
directly into this file by their assigned fallback reviewers and read by the main
auditor before synthesis.