# Mode C Performance Opposition

Mode C review ID: PERF-20260804-001
Patch/review file: not applicable; this is the Mode C performance artifact
Opposition file: docs/bug_hunts/performance_reviews/PERF-20260804-001-opposition.md
Mode path: C
Target: Windows responsiveness and maintenance-scan performance
Performance symptom: Dashboard GPU detection took 4.013s, process enumeration took 13.446s, dashboard collection took 7.072s, and a live Downloads scan exceeded the 120s benchmark window on the validation host.
Allowed behaviour changes: explicitly requested Windows Known Folder resolution and Recycle Bin sizing; none elsewhere
Files changed: algo.py, maintenance/actions.py, maintenance/dialogs.py, maintenance/scanner.py, tests/test_maintenance.py, tests/test_window.py, window.py
Baseline evidence: see the main auditor summary below
Correctness validation: baseline 21 unittest tests passed; Ruff passed
Performance validation: before measurements captured; after measurements pending
Research pack used: main_auditor_research_pack.md; official Microsoft Shell API documentation
Adversarial threshold: full A4

## Main Auditor Candidate Summary

**Optimization made:** Added dashboard request coalescing, process metadata batching with cancellation, per-scanner static GPU caching, `os.scandir` Downloads/trash traversal, metadata-keyed duplicate-hash caching, progress/cancellation delivery, Windows Known Folder resolution, and Windows Recycle Bin sizing through Shell APIs.

**Claimed performance win:** Preserve dashboard and maintenance results while reducing repeated Windows GPU subprocess work, per-process lookups, duplicate hashing, and overlapping scans.

**Before measurement:**

- `python -m unittest discover -s tests -v`: 21 passed in 0.453s.
- `ruff check .`: passed.
- `SystemScanner.gpu_details()`: 4.013s.
- `SystemScanner.scan_processes()`: 13.446s for 110 candidates.
- `SystemScanner.trash_size()`: 0.000s and 0 bytes on the Windows host.
- `SystemScanner.scan_dashboard()`: 7.072s for 6 resources.
- Live `SystemScanner.scan_downloads()` benchmark: exceeded 120s without a result.
- Controlled duplicate fixture with two 8 MiB identical files: median 0.205s across three scans.

**After measurement:**

- `python -m unittest discover -s tests -v`: 29 passed.
- `ruff check .`: passed.
- Changed-file `ruff format --check`: passed.
- `SystemScanner.gpu_details()`: cold 6.098s, cached 0.002s on one run; cold timing is host/process noisy.
- `SystemScanner.scan_processes()`: 11.094s for 120 candidates on one run versus 13.446s for 110 before; candidate count and host state varied.
- `SystemScanner.scan_dashboard()`: cold 10.807s, cached 0.786s on one run; cold timing is host/process noisy.
- Controlled duplicate fixture with two 8 MiB identical files: cold median 0.093s across five independent scanner instances and repeated-scan median 0.001s after warm-up.
- Live Downloads scan remained over 120s; it emitted bounded progress events and was terminated by the benchmark timeout, not treated as a pass.

**Correctness evidence:** 29 repository tests pass, including hash-cache invalidation, cancellation, GPU-cache, Windows Known Folder, Recycle Bin, dashboard coalescing, and stale-request replay tests.

**Public contracts that must remain unchanged:** `Analyzer` method names and default call shapes, `DashboardSnapshot`, `ProcessCandidate`, `FileCandidate`, `ProcessActionResult`, `FileActionResult`, process protection and user checks, `send2trash` usage, UI confirmation flows, and platform fallback output contracts.

**Security/privacy/fail-closed boundaries:** No permanent deletion; Downloads root validation remains resolved-path based; protected processes remain unselectable; process actions remain same-user only; worker errors remain visible; no user data is printed by benchmark commands.

**High-risk surfaces touched:**

- cache: yes, bounded to one scanner instance and file metadata
- DB/query/session: no
- async/job/retry/idempotency: no external jobs; local worker overlap/cancellation is touched
- browser/provider: no
- auth/session/CSRF/CORS/admin: no
- logging/redaction/privacy: no intentional change
- OCR/evidence integrity: no
- CSV/export exact output: no
- settings/runtime config: no
- template/static output: no
- native/Rust/frontend/build: Windows `ctypes` Shell API boundary

**Mode transition history:**

```text
Mode path: C
Transition reasons: Performance-only request; no correctness bug identified so far.
Current final mode: C
```

---

## Opposer 1 — Reproduction and Measurement Skeptic

**Repo evidence checked:**

- `maintenance/scanner.py:122-132` makes dashboard timing include live `psutil` calls and `gpu_details()`; the GPU cache is per `SystemScanner` instance at `:653-679`.
- `maintenance/scanner.py:233-323` still enumerates processes and sleeps for `0.25s`; it has no warm result cache, so process-count and host-state changes directly affect comparison.
- `maintenance/scanner.py:325-354`, `:356-408`, and `:447-507` show that Downloads timing includes the complete tree walk, duplicate grouping, and file hashing. The cache is bounded to the scanner instance and keyed by file metadata at `:617-651`.
- `tests/test_maintenance.py:62-87` proves hash-cache reuse/invalidation by call count, not a stable performance distribution; the cancellation test at `:89-107` does not exercise a live tree.
- The candidate summary records a live Downloads timeout both before and after, and compares process runs with different candidate counts.

**Commands run:**

- `python -m unittest discover -s tests -v` -> 29 passed in 0.289s.
- `ruff check .` -> passed.
- `ruff format --check algo.py maintenance/actions.py maintenance/dialogs.py maintenance/scanner.py tests/test_maintenance.py tests/test_window.py window.py` -> passed.
- An inline `python -c` timing harness used `time.perf_counter()` around `gpu_details()` twice, `scan_processes()` twice, and `scan_dashboard()` twice on one scanner; it also used a temporary directory containing two identical 8 MiB files, ran two scans on one scanner, and one scan on a fresh scanner.
- A second inline `python -c` harness loaded `HEAD:maintenance/scanner.py` with `git show` into an in-memory module, without changing the worktree, and ran the same measurements against the current scanner and the same temporary fixture.
- A child-process `python -c` live scan of `SystemScanner().scan_downloads()` was bounded by a 20s parent timeout; the child was terminated on timeout.

**Measurement challenge:**

```text
Command: Current working-tree timing harness described above.
Input/fixture: Current host; one SystemScanner for repeated GPU/process/dashboard calls; two identical 8 MiB temporary files for synthetic duplicate scans.
Result: GPU 1.841s -> 0.001s (3 detail lines); processes 9.592s/117 candidates -> 9.338s/118; dashboard 3.177s/6 resources -> 0.328s/6; synthetic scan 0.288s/1 candidate -> 0.001s/1, with a fresh scanner at 0.104s/1.
Interpretation: Warm GPU/dashboard/hash-cache effects reproduce. The labels are only scanner-cache cold/warm, not cold OS, process, or disk measurements. Process timing is effectively unchanged and the input set changed between runs.
```

```text
Command: In-memory HEAD-vs-current timing harness.
Input/fixture: Same host and two identical 8 MiB temporary files; each implementation measured with a fresh scanner, then repeated on that scanner where relevant.
Result: HEAD/current GPU 2.861s/3.326s vs 2.035s/0.001s; process 9.841s/109 vs 7.951s/107; dashboard 4.149s -> 1.809s vs 2.362s -> 0.292s; synthetic 0.192s -> 0.090s vs 0.087s -> 0.001s, with one candidate from each.
Interpretation: The direction supports the cache optimization, especially for repeated calls, but it is one noisy host run and process counts differ. It does not validate a general cold-start or end-to-end improvement.
```

```text
Command: Child-process live SystemScanner().scan_downloads() with a 20s parent timeout.
Input/fixture: The actual default Downloads path; no files were changed and output was suppressed.
Result: TIMEOUT at 20s; no result count or completed duration.
Interpretation: This is an honest timeout, not a pass or a speedup. The candidate's recorded >120s before and >120s after results leave the real Downloads before/after comparison unresolved.
```

The two-file synthetic fixture demonstrates cache reuse but is not representative of the timed-out live tree. The passing correctness suite establishes that the benchmarked methods execute and that selected cache/cancellation behaviours are tested; it does not establish measurement repeatability or prove that the live hot path completes.

**Verdict:** Needs more evidence. The warm-cache improvements are reproducible and the patch's timeout reporting is honest, but the principal real-path Downloads claim is unmeasured, cold timings are host/cache noisy, and process comparisons are not workload-matched. Accepting the performance claim requires a bounded, repeatable live-tree benchmark or a deliberately narrower claim limited to the demonstrated warm-cache paths.

---

## Opposer 2 — Repo-truth and Contract Skeptic

**Repo evidence checked:**

- `algo.py:270-290` and `HEAD:algo.py` for the public analyzer methods and their default delegation shapes.
- `maintenance/models.py:6-61` for the unchanged frozen dataclass result fields.
- `maintenance/scanner.py:233-354,356-507,522-679,791-860` and `HEAD:maintenance/scanner.py` for process/file result construction, ordering, cancellation, cache keys, platform fallbacks, and protected-user predicates.
- `maintenance/actions.py:107-214` for process protection, same-user checks, `send2trash`, and resolved Downloads-root validation.
- `maintenance/dialogs.py:21-74,339-388,675-766` and `window.py:342-437,562-577` for worker call shapes, cancellation, close fencing, request coalescing, and stale-result handling.
- `tests/test_maintenance.py`, `tests/test_storage_dialog.py`, and `tests/test_window.py` for the repository's existing result, action, and lifecycle assertions.

**Commands run:**

- `python -m unittest discover -s tests -v` -> 29 passed in 0.233s.
- `ruff check .` -> passed.
- `ruff format --check algo.py maintenance/actions.py maintenance/dialogs.py maintenance/scanner.py tests/test_maintenance.py tests/test_window.py window.py` -> 7 files already formatted.
- Isolated legacy-delegation probe -> `Analyzer.process_candidates()` and `Analyzer.storage_candidates()` each raised `TypeError` when given a scanner implementing the previous no-argument methods.
- Isolated legacy-monkeypatch probe -> a one-argument `_file_hash` replacement raised `TypeError` because the new caller passes `cancel_event=None`.
- Isolated `process_iter` probe -> a previous no-argument fake raised `TypeError` on the new `attrs=` call.
- Isolated traversal probe -> current equal-size nested output was `['b/file.bin', 'a/file.bin']`, while `root.rglob('*')` produced `['a/file.bin', 'b/file.bin']`.
- Isolated iterator-failure probe -> an `os.scandir` iterator `OSError` escaped as `OSError: directory changed during scan`.
- Isolated process-safety probe -> protected name and foreign user were `action_allowed=False`, a domain-qualified current user was `True`, and the scanner process was protected; the expected predicates remain intact.

**Contract challenge:**

```text
Contract: scan_downloads() must preserve the existing FileCandidate set, observable ordering, and fail-soft filesystem behaviour.
Evidence before: HEAD uses root.rglob("*") inside an outer OSError handler. Candidates are then sorted only by size, so equal-size ties retain the traversal insertion order.
Evidence after: The replacement uses a LIFO pending_directories stack at scanner.py:362-368. The nested equal-size probe changed the observable order from a/b to b/a. The new for entry in entries block has a finally but no OSError handler around iterator __next__ failures; the failure probe propagated OSError instead of returning the partial stats that the old outer handler returned.
Risk: Storage rows and hidden order-sensitive tests can change, and a transient directory race now reaches the worker error dialog instead of preserving the prior partial scan result. This is a confirmed behaviour-preservation failure independent of the benchmark result.
```

```text
Contract: Analyzer.process_candidates() and Analyzer.storage_candidates() retain their no-argument default delegation and compatible scanner/test-double surfaces.
Evidence before: HEAD calls self.scanner.scan_processes() and self.scanner.scan_downloads() with no keyword arguments.
Evidence after: algo.py:279 and :287-290 always pass cancel_event=None and progress_callback=None, respectively. A legacy scanner with the old methods raised unexpected-keyword TypeError. ProcessDialog and StorageDialog also pass new keyword arguments to injected analyzer objects, and their scan paths call run_in_thread with new keyword-only parameters.
Risk: Existing subclasses, injected fakes, or hidden tests that implement the documented/default no-argument surface fail before returning a dataclass result. The actual current SystemScanner works, so this is a compatibility regression at the delegation/monkeypatch boundary rather than a default-host failure.
```

```text
Contract: Existing hidden-test-sensitive monkeypatch points must remain callable with their established shapes.
Evidence before: HEAD._file_hash accepted (path) and scan_processes used psutil.process_iter() without attrs; _download_file_stats was driven by Path.rglob().
Evidence after: _cached_file_hash() calls _file_hash(path, cancel_event) even when the event is None; scan_processes() calls psutil.process_iter(attrs=[...]) twice; _download_file_stats() no longer consults Path.rglob(). The isolated one-argument hash fake and no-argument process_iter fake both failed with TypeError.
Risk: Existing test doubles and callers that patch these seams no longer exercise the intended code and can fail with TypeError or silently stop controlling traversal. These are private seams, so the runtime impact is limited, but the patch needs explicit compatibility evidence before treating the hidden-test-sensitive surface as preserved.
```

```text
Contract: With Allowed behaviour changes: none, platform fallback output and the default cleanup root must remain equivalent.
Evidence before: On Windows, HEAD._trash_paths() returned an empty tuple, so trash_size() was 0; _default_downloads_path() checked OneDrive\\Downloads before USERPROFILE\\Downloads.
Evidence after: scanner.py:522-577 returns the Shell API's non-zero Recycle Bin size, and scanner.py:791-803 prefers SHGetKnownFolderPath before the OneDrive/environment fallback. FileManager now adopts that changed default at actions.py:164-167.
Risk: DashboardSnapshot storage details can change from 0 bytes, and default scans/validated send2trash scope can move from an environment-selected OneDrive path to the Shell-known path. The process protection, same-user check, dataclass fields, send2trash call, resolved-root check, and fallback-to-0/error paths were otherwise preserved, but these successful-platform changes are behaviour/scope changes rather than pure performance improvements and require explicit scope approval or parity tests.
```

```text
Contract: Each ProcessCandidate should represent one process snapshot while preserving filtering, ordering, and action safety.
Evidence before: HEAD enumerated one Process object list and read its as_dict(), cpu_percent(), and memory_percent() values from that object.
Evidence after: scanner.py:241-267 enumerates a second process set and maps metadata by PID, then scanner.py:278-320 combines that metadata with CPU data from the first set. A process exit/restart or PID reuse between passes can mix records from different process identities; a PID absent from the second pass is silently filtered. The safety predicates themselves remain unchanged, and the isolated fake confirmed protected-name, foreign-user, and domain-qualified same-user results.
Risk: A short process churn window can produce a mismatched ProcessCandidate or omit a candidate, so the batching optimization needs a process-identity/churn test before its result contract can be accepted.
```

**Verdict:** Unsafe for unconditional Mode C acceptance; the traversal/failure and platform-output changes are concrete contract deviations, while the delegation/monkeypatch and process-snapshot surfaces need explicit compatibility evidence or a narrower approved scope.

---

## Opposer 3 — Architecture, Security, and Failure-Mode Skeptic

**Repo evidence checked:**

- `maintenance/scanner.py:100-104,447-507,610-651` for the per-scanner hash cache, its fingerprint, pruning, and duplicate classification.
- `maintenance/scanner.py:233-354,356-408,438-507` for process and Downloads cancellation checkpoints, traversal, progress delivery, and failure timing.
- `maintenance/dialogs.py:21-74,339-388,675-766` for worker delivery, generation fencing, cancellation, and dialog close handling.
- `window.py:342-437,562-577` for dashboard coalescing, callback fencing, and root shutdown; `maintenance/actions.py:107-214` for process revalidation and Trash scope.
- `maintenance/scanner.py:522-577,791-844` for the Windows Shell calls, COM cleanup, known-folder fallback, and Recycle Bin reporting.
- The existing 29-test suite and the candidate summary. The tests cover basic cache reuse/invalidation, but not same-fingerprint rewrites, concurrent scanners, close-time worker completion, COM ABI details, or domain-qualified identity.

**Commands run:**

- `python -m unittest discover -s tests -v` -> 29 passed in 0.217s.
- `ruff check .` -> passed; changed-file `ruff format --check` -> passed; `git diff --check` -> no whitespace errors.
- Windows read-only API probe -> `_windows_downloads_path()` returned a value and `_windows_trash_size()` returned an integer. `SHGetKnownFolderPath` and `SHQueryRecycleBinW` both had `argtypes is None` even though `restype` was assigned.
- Temporary-file fingerprint probe -> `fingerprint_unchanged_after_same_size_rewrite True`, `content_changed True`, and `stale_hash_reused True` after restoring the original mtime.
- Temporary-file cache-growth probe -> 200 same-size files left `hash_cache_entries_after_200_files 200`.
- Cancellation probe -> `large_classification_entered_after_cancel True` after cancellation was set during cache pruning.
- Two-thread GPU-cache probe -> `concurrent_fallback_loader_calls 2` with identical results, proving the static cache does not coalesce concurrent misses.
- Close/failure probes -> `dashboard_worker_still_blocked_after_close True`; a fake Tk `after()` raising `RuntimeError` produced `delivery_error_callback_count 0` and an unhandled worker exception; an unavailable GPU fallback loader ran twice.
- Known-folder fallback probe -> a successful but nonexistent known-folder result was selected even when an existing OneDrive fallback was available. The identity probe returned `different_domains_same_username_accepted True` for `EVIL\\sameuser` versus `LOCAL\\sameuser`.
- Microsoft Learn `SHGetKnownFolderPath` and `SHQueryRecycleBinW`, plus Python `ctypes` foreign-function documentation, were checked for pointer ownership, structure size, HRESULT, and prototype semantics.

**Failure-mode challenge:**

```text
Failure mode: The duplicate cache serves a digest for changed file content.
Before behaviour: HEAD hashed each duplicate candidate during each scan; there was no retained digest to reuse.
After behaviour: The cache key is only (path, size, st_mtime_ns, st_ctime_ns). On this Windows host a same-size rewrite with the original mtime restored kept that fingerprint unchanged while changing the bytes, and _cached_file_hash() returned the old digest.
Safety verdict: Confirmed correctness and cleanup-safety blocker. A file can be presented as a duplicate when it is not, and the user can then select that wrong candidate for send2trash. Trash is reversible, but result integrity and the stated behaviour-preservation contract are not preserved.
```

```text
Failure mode: Cache memory is described as bounded but has no size bound.
Before behaviour: No hash data survived a scan.
After behaviour: _prune_hash_cache() removes missing or changed paths but retains one path/digest entry for every current file, and the scanner lives for the application lifetime. The 200-file probe retained 200 entries; there is no maximum entry count or byte budget. The cache is instance-local and not persisted or logged, so no cross-user leak was found, but instance locality is not a memory bound.
Safety verdict: Confirmed P2 reliability/performance risk and evidence gap for a high-risk cache change. Large Downloads trees can turn the optimization into unbounded retained private path/digest metadata.
```

```text
Failure mode: Concurrent scanners defeat cache guarantees and can race cache pruning.
Before behaviour: Independent scans did not share mutable cache state.
After behaviour: Multiple dialogs can share the same Analyzer/SystemScanner. The hash lock covers dictionary operations only, not the check/read/hash/store transaction; _prune_hash_cache() replaces the whole map from one scan's file set. The GPU cache has no lock, and two synchronized callers invoked the fallback loader twice.
Safety verdict: No wrong result was reproduced from concurrency alone, and the dictionary operations are individually protected. The claimed repeated-work reduction is not concurrency-safe, and concurrent scans can redo hashes or evict another scan's warm entries. This needs a serialized/cache-generation test before acceptance.
```

```text
Failure mode: Cancellation arrives after traversal but before classification, or during close.
Before behaviour: The old path had no cancellation contract, but it also did not advertise a cancellable worker or leave a cancellation control in the UI.
After behaviour: scan_downloads() checks cancellation during traversal and hashing, but _prune_hash_cache(), _mark_large_downloads(), and the 0.25 second process sleep have no checkpoint. The probe set the event during pruning and observed large-file classification still enter. Dialog close only sets the event and never joins the daemon worker; dashboard close has no event at all.
Safety verdict: Confirmed responsiveness/lifecycle gap. A large tree can continue CPU and metadata work after the user cancels, and a dashboard scan can continue GPU/psutil work after the window is closed. No permanent action occurs in these scanner workers, but shutdown does not mean work has stopped.
```

```text
Failure mode: Worker-to-Tk delivery fails while the event loop is stopping or unavailable.
Before behaviour: A normal worker completion was delivered through the existing Tk callback path.
After behaviour: run_in_thread() catches tk.TclError around widget.after() but not RuntimeError. A read-only fake-widget probe made after() raise RuntimeError; the on_error callback was never called and the worker terminated with an unhandled exception. The affected dialog state cannot be reset by that callback.
Safety verdict: Confirmed failure-observability/lifecycle gap. Normal generation guards prevent stale success/error/progress updates after a destroyed widget, and no stale UI bypass was reproduced, but the close/error path is not fully fenced for the documented non-mainloop failure mode.
```

```text
Failure mode: A Windows Shell failure is presented as valid empty data or repeated expensive failure.
Before behaviour: On Windows HEAD returned zero Trash bytes without calling the Shell and used the environment fallback for Downloads.
After behaviour: _windows_trash_size() converts API/ctypes failures to 0 with no error marker; a failed GPU fallback is deliberately not cached and reruns its potentially 10-second subprocess on every dashboard scan. Also, any non-null SHGetKnownFolderPath result is accepted without checking existence, so a missing known folder wins over an existing OneDrive fallback in the probe.
Safety verdict: Confirmed failure-timing/observability and output-scope risks. The live Shell calls succeeded and the COM path was not shown to leak, but failure and stale-redirection cases are not equivalently visible or bounded.
```

```text
Failure mode: Windows ctypes ABI or COM ownership is wrong on a machine/API variant not covered by mocks.
Before behaviour: No Shell API call was present in this code path.
After behaviour: The structure fields and cb_size match the documented SHQUERYRBINFO shape. _windows_downloads_path() copies the returned string into Path, frees the CoTaskMem allocation in finally, and calls CoUninitialize only after S_OK/S_FALSE, which the live probe exercised successfully. However, all native functions have unset argtypes; the tests only use Python fakes and cannot validate pointer conversion or HRESULT ABI.
Safety verdict: Ownership/COM handling is provisionally sound, not a confirmed defect. Native integration remains incomplete evidence; explicit prototypes and a failure-path test are required before treating this boundary as fully validated.
```

```text
Failure mode: A process from another Windows authority is treated as the current user.
Before behaviour: The existing scanner/action helper normalized both values by stripping the domain and comparing only the suffix.
After behaviour: The process batching change leaves that helper and the action-layer revalidation intact. The probe returned true for EVIL\\sameuser versus LOCAL\\sameuser, so the summary's "same-user only" statement is not authority-aware.
Safety verdict: No new bypass was introduced by the batching diff: protected PIDs/names and current username checks are still repeated by ProcessManager immediately before terminate/kill, and the focused safety probes passed. This is a pre-existing security residual that must not be counted as proof of a strong same-user boundary.
```

```text
Failure mode: Cleanup crosses the permanent-delete boundary or bypasses the root check.
Before behaviour: FileManager resolved the selected path, required a regular file inside allowed_root, required confirmation in the dialog, and called send2trash rather than unlink/remove.
After behaviour: Those checks and the confirmation text remain; the Windows change only supplies the Shell-known Downloads root and makes trash_size() read-only. No permanent-delete call was found, and the installed Windows send2trash implementation uses recycle/undo flags.
Safety verdict: No new permanent-delete bypass found. The stale hash finding above can still cause the wrong file to be moved to Trash, so the Trash boundary is preserved but candidate identity is not.
```

**Verdict:** Unsafe for unconditional Mode C acceptance. The same-fingerprint rewrite is a confirmed result-integrity and cleanup-safety regression; the cache is not size-bounded, cancellation/close is cooperative without worker lifecycle fencing, and Windows failure output is silently collapsed or retried. Stale callback checks, COM allocation cleanup, protected-process revalidation, and the no-permanent-delete call boundary appear intact, but those non-findings do not offset the confirmed cache blocker and missing high-risk evidence.

---

## Opposer 4 — External Semantics and Docs Skeptic

**Research question:** Do the added Windows Shell/ctypes calls, replacement `os.scandir` traversal, batched `psutil` enumeration, and Tk worker delivery satisfy their documented contracts while preserving the prior fail-soft and cancellation behaviour?

**External docs used:**

- Microsoft Learn: [`SHGetKnownFolderPath`](https://learn.microsoft.com/en-us/windows/win32/api/shlobj_core/nf-shlobj_core-shgetknownfolderpath), [`CoInitializeEx`](https://learn.microsoft.com/en-us/windows/win32/api/combaseapi/nf-combaseapi-coinitializeex), [`CoUninitialize`](https://learn.microsoft.com/en-us/windows/win32/api/combaseapi/nf-combaseapi-couninitialize), and [`CoTaskMemFree`](https://learn.microsoft.com/en-us/windows/win32/api/combaseapi/nf-combaseapi-cotaskmemfree) document the returned allocation ownership and the requirement to balance successful COM initialization (`S_OK` or `S_FALSE`) on the same thread.
- Microsoft Learn: [`SHQueryRecycleBinW`](https://learn.microsoft.com/en-us/windows/win32/api/shellapi/nf-shellapi-shqueryrecyclebinw) and [`SHQUERYRBINFO`](https://learn.microsoft.com/en-us/windows/win32/api/shellapi/ns-shellapi-shqueryrbinfo) document the `HRESULT` result, optional null root, `cbSize` initialization, and 64-bit size/count fields.
- Python 3.12 documentation: [`os.scandir`](https://docs.python.org/3.12/library/os.html#os.scandir), [`Path.rglob`](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path.rglob), [`ctypes` function prototypes](https://docs.python.org/3.12/library/ctypes.html#ctypes-function-prototypes), [`threading.Event`](https://docs.python.org/3.12/library/threading.html#event-objects), and the [`tkinter` threading model](https://docs.python.org/3.12/library/tkinter.html#threading-model).
- Official psutil API source: [`docs/api.rst`](https://raw.githubusercontent.com/giampaolo/psutil/master/docs/api.rst), including `process_iter(attrs=...)`, cached `Process.info`, and process-identity caveats.
- Official send2trash documentation: [`README.rst`](https://raw.githubusercontent.com/arsenetar/send2trash/master/README.rst), which describes moving paths to the platform Trash/Recycle Bin rather than permanently deleting them.

**Repo-specific implication:**

- The Windows ownership sequence is provisionally correct. `scanner.py:806-844` copies the known-folder string before freeing the `CoTaskMem` allocation and calls `CoUninitialize` only after `S_OK`/`S_FALSE`; `scanner.py:567-577` initializes `cb_size` and treats a nonzero `HRESULT` or negative size as failure. Read-only Windows calls returned a known-folder value and a nonnegative Recycle Bin size. However, `scanner.py:570-571` and `:820-827` leave `argtypes` unset. The calls currently work on this host, but the ctypes boundary is not strongly type-checked and the tests use Python fakes rather than native failure cases. This is an ABI evidence gap, not a reproduced ownership defect.
- `SHGetKnownFolderPath` returning a path does not itself establish that the directory currently exists. `scanner.py:793-795` accepts every non-null result before checking existence, so a stale or unavailable known-folder redirection can suppress the existing OneDrive/home fallback and change both the scan root and the FileManager cleanup scope.
- `os.scandir` documents an iterator whose `__next__` operation can raise `OSError`, while `scanner.py:369-393` catches only the initial `os.scandir(directory)` call and per-entry operations. A read-only probe produced `scandir_iterator_error_escaped OSError iterator failure`; the previous `Path.rglob()` implementation had an outer `OSError` handler. This is a confirmed fail-soft regression. `follow_symlinks=False` is correctly used for entry checks, but neither traversal API promises a stable order, so equal-size candidate ordering must not be treated as preserved without an explicit sort.
- `psutil.process_iter(attrs=...)` supplies prefetched `Process.info` values and may reuse cached `Process` objects, but a second iterator is not an atomic snapshot. `scanner.py:241-284` waits, enumerates again, and joins metadata to the first pass by PID. A process exit/restart or PID reuse can therefore omit a row or combine CPU data and metadata from different process instances. The local probe confirmed repeated iteration reused the object and populated the requested `info` keys; it cannot prove identity safety across process churn.
- `threading.Event` is cooperative cancellation, not worker termination. The scanner has no checkpoint during `time.sleep(0.25)`, cache pruning, or large-file classification, and closing a dialog does not join its daemon worker. Tkinter's threading model also requires a live Tcl event loop for cross-thread `after()` delivery. `run_in_thread()` catches `tk.TclError` but not `RuntimeError` at `dialogs.py:46`, `:65`, and `:70`; a fake-widget probe produced `after_runtimeerror_uncaught ['RuntimeError']`. The worker exception is therefore unreported when teardown fails through that documented boundary.
- The `send2trash` call remains consistent with its documented reversible Trash/Recycle Bin contract, and no permanent-delete API was introduced. The main external safety concern is the changed known-folder root, not the `send2trash` invocation itself.

**Local evidence still needed:**

- Completed read-only checks: `python -m unittest discover -s tests -v` -> 29 passed; `ruff check .` -> passed; `git diff --check` -> no whitespace errors; native Windows known-folder and Recycle Bin calls succeeded; `SHGetKnownFolderPath.argtypes` and `SHQueryRecycleBinW.argtypes` were both `None`.
- Remaining evidence for a fully validated native boundary is an explicit-prototype/failure-path test using real Windows calls, plus a fallback test where the known-folder path is returned but absent.
- Remaining evidence for the process path is a controlled process-churn or identity test proving that the two enumerations cannot mix records. Remaining lifecycle evidence is a real Tk teardown test that verifies worker exceptions are surfaced or deliberately suppressed.

**Verdict:** Unsafe for unconditional Mode C acceptance under `Allowed behaviour changes: none`. The Windows COM allocation and Recycle Bin structure handling are provisionally sound, and `send2trash` remains reversible, but the replacement traversal can escape an `OSError`, the two-pass process join is not an atomic identity-safe snapshot, Tk delivery can terminate with an unhandled `RuntimeError`, and a non-existent known-folder result can change the cleanup scope. Missing ctypes prototypes and native failure-path coverage keep the Shell boundary below full A4 evidence even though no native ownership bug was reproduced.

---

## Agent 5 — Mode C Superpower Evidence Auditor

**Threshold declared in header:** full A4

**Agent 5 required by this threshold:** yes

**Reasoning:** Full A4 is required because this patch changes cache lifetime and invalidation, worker cancellation and close behaviour, process enumeration, user-visible filesystem roots, and Windows native API calls while claiming no behaviour changes. All four Opposer sections were present before this independent fallback audit. I read the complete artifact, current diff, exact changed code and tests, recorded commands and measurements, the Mode C guidance, and the cited official Microsoft and Python documentation. The registered Agent 5 could not write the artifact, so this section is the portable independent fallback; no application code or normal tests were changed.

**Agent 5 run for this review:** yes

**Reason Agent 5 was/was-not run:** The registered Agent 5 was unavailable for artifact writing. This fallback ran independently after Opposers 1-4 and wrote this section directly.

**Evidence completeness:** Sufficient to make a reject/transition decision, but not sufficient to accept the patch. The repository suite passes at 29 tests and Ruff plus changed-file format checks pass. Independent read-only probes reproduced `fingerprint_unchanged True`, `content_changed True`, and `stale_hash_reused True` after a same-size rewrite with the original timestamp restored; 200 same-size files left 200 entries in `_hash_cache`; a broken `os.scandir` iterator raised `OSError` from `_download_file_stats`; two concurrent GPU fallback calls invoked the loader twice; and a fake Tk widget produced zero error-callback calls plus an uncaught `RuntimeError`. A process-churn double also produced one `ProcessCandidate` combining the first process object's CPU value with replacement metadata. These are direct probes of the current working tree, not inferred findings.

**Correctness-before-speed check:** The baseline and post-edit unit suites are green, but the correctness gate does not pass for unconditional Mode C acceptance. The added tests cover normal cache reuse, mtime invalidation, basic cancellation, successful known-folder selection, and a fake Shell query; they do not cover same-fingerprint content replacement, cache capacity, iterator failure, process identity churn, concurrent cache misses, close-time worker completion, `RuntimeError` delivery failure, or native failure/prototype paths. The independent counter-tests found correctness and lifecycle regressions, so the warm-cache timing cannot rescue the patch.

**Performance measurement check:** The measurements are honest but narrow. The live Downloads scan timed out both before and after and is not evidence of a speedup. Process comparisons used different candidate counts (110 versus 120), and current cold GPU/dashboard timings were slower than the recorded baseline while warm calls were much faster. The controlled two-file duplicate fixture demonstrates cache reuse and is useful for that local claim, but it is not representative of the timed-out live tree. The defensible claim is limited to repeated calls within a scanner instance; no general cold-start or end-to-end maintenance improvement was established.

**Contract preservation check:** Unsafe under `Allowed behaviour changes: none`.

- `algo.py:274-290` always forwards new keyword arguments. An injected legacy scanner with no-argument `scan_processes()` or `scan_downloads()` now raises `TypeError`, so the existing Analyzer delegation/test-double surface is not preserved.
- `maintenance/scanner.py:356-408` replaces the prior `Path.rglob()` traversal and outer `OSError` handling with a LIFO `os.scandir` walk. Equal-size nested results changed order in the recorded probe, and an iterator `OSError` now escapes instead of returning the prior partial result.
- `maintenance/scanner.py:233-323` obtains metadata in a second process enumeration and joins it to the first pass by PID. The independent double reproduced mixed-object output; PID reuse or process replacement can therefore change or combine a `ProcessCandidate` snapshot.
- `maintenance/scanner.py:522-577` and `:791-803` change successful Windows output and the default cleanup root, including `FileManager` construction, rather than only reducing work. That is a public/output and cleanup-scope change requiring explicit approval or parity evidence.

**Security/privacy/fail-closed check:** The permanent-delete boundary, `send2trash` call, resolved-root validation, protected-process filtering, and generation checks remain visible in the current code. The cache is scanner-local, in-memory, and not logged, so no cross-user or persisted-data leak was reproduced. However, the stale digest can mark a changed non-duplicate as a duplicate and expose the wrong file to a user-selected Trash action; result identity and cleanup safety are therefore not preserved. The retained path/digest map has no capacity bound, and the 200-file probe confirms that "instance-local" is not a memory bound. The domain-stripping same-user weakness is pre-existing and was not counted as a patch-introduced bypass.

**Failure timing check:** Unsafe. Cancellation is cooperative and has no checkpoint during cache pruning, large-file classification, or the process sleep; dialog close sets an event but does not join the daemon worker, and dashboard close has no cancellation event. `run_in_thread()` catches `tk.TclError` but not `RuntimeError` around cross-thread `after()` delivery, which the independent probe reproduced as an unreported worker exception. Windows Shell failures collapse to zero, a missing known-folder directory can suppress an existing fallback, and failed GPU fallback calls are deliberately retried rather than bounded. These alter failure visibility, timing, or post-close work.

**High-risk surface check:** Not fully validated. Cache invalidation is demonstrably insufficient for same-size/same-timestamp rewrites; the cache check/hash/store sequence is not atomic and concurrent misses are not coalesced; there is no maximum cache size; process enumeration is not an atomic identity-safe snapshot; cancellation and worker close are not lifecycle-fenced; and the Windows boundary has only fake failure coverage. The native local probe did succeed, returned a nonnegative Recycle Bin size, and reported a 24-byte recycle structure, while `SHGetKnownFolderPath.argtypes` and `SHQueryRecycleBinW.argtypes` were both `None`. Microsoft documentation supports freeing the known-folder allocation with `CoTaskMemFree`, balancing successful `CoInitializeEx` calls on the same thread, setting `cbSize`, and checking HRESULTs; the current ownership sequence is provisionally sound, but missing prototypes and native failure-path coverage leave the ABI contract below full-A4 evidence.

**Mode transition check:** Required before acceptance. The reproduced stale-cache, traversal/failure, delegation, process-snapshot, and worker-lifecycle issues are introduced by this performance patch, so the correct repair path is an explicit `C -> A` transition, followed by fresh correctness and adversarial validation before any renewed Mode C performance claim. The pre-existing domain-qualified username issue does not independently require a `C -> B` transition; it must not be used as evidence that the new batching change is safe.

**Missing evidence:** A bounded, workload-matched live Downloads comparison; exact-content cache invalidation including path replacement; a documented cache capacity/privacy policy; serialized or generation-safe concurrent scanner tests; process churn/PID-reuse evidence; cancellation during pruning/classification/sleep and worker join/close tests; Tk teardown tests covering both `TclError` and `RuntimeError`; known-folder existence/fallback tests; explicit ctypes prototypes and native failure-path tests; and a complete post-repair correctness run. No LR executable or LR/drift output was available in this workspace, and no type-checker result was supplied.

**Blocking issues:** The stale hash can produce a wrong duplicate candidate and wrong Trash target. The new traversal can raise on a directory iterator race. Analyzer compatibility can fail before returning results. The two-pass process join can produce a mixed process snapshot. Dialog/dashboard workers can continue after close, and a Tk delivery failure can become an uncaught exception. The unbounded cache and unverified native prototypes also block the stated high-risk no-behaviour-change claim.

**Non-blocking issues:** Warm GPU/dashboard/hash-cache improvements are reproducible only on the demonstrated local paths; cold and live-tree claims remain unresolved. Concurrent GPU fallback misses duplicate work. Shell failure-to-zero behaviour and the missing-known-folder existence check need an explicit output/fallback contract. The existing username normalization concern remains a separate security follow-up, not a new regression.

**Agent 5 final verdict:** Transition required. Do not accept this as a behaviour-preserving Mode C optimization. Repair the patch under an explicit `C -> A` correctness transition, then rerun the required correctness, native/lifecycle, and full-A4 evidence gates before returning to Mode C.

---

## Test and Measurement Evidence Synthesis

| Evidence | Path/command | What it tested/measured | Result | Supports patch | Challenges patch | Gaps |
|---|---|---|---|---|---|---|
| Correctness baseline | `python -m unittest discover -s tests -v` | Existing repository tests | 21 passed | Yes | No | Focused tests pending |
| Static baseline | `ruff check .` | Existing lint surface | Passed | Yes | No | Post-edit checks pending |
| Before measurement | Inline Python timing command | GPU, process, dashboard, trash paths | See summary | Yes | Live Downloads scan timed out | After comparison pending |
| Duplicate fixture | Inline Python timing command | Two 8 MiB duplicate files | Median 0.205s | Yes | Synthetic fixture | Real Downloads scan unavailable |
| Opposer 1 challenge | Pending | Measurement honesty | Pending | | | |
| Opposer 2 challenge | Pending | Contract preservation | Pending | | | |
| Opposer 3 challenge | Pending | Failure and security boundaries | Pending | | | |
| Opposer 4 challenge | Pending | Official API/library semantics | Pending | | | |
| Agent 5 audit | Pending | Evidence completeness and final safety | Pending | | | |

## Main Auditor Final Synthesis

**Did correctness validation pass before performance claims?** Yes for the baseline; post-edit result pending.

**Is the before/after comparison honest?** Before evidence is recorded; after evidence pending. The live Downloads timeout is reported as a timeout, not a timing result.

**Was the real hot path measured?** Yes for dashboard, GPU, process, and trash paths; the live Downloads path did not complete within the benchmark window.

**Were public contracts preserved?** Pending post-edit review.

**Were security/privacy/fail-closed boundaries preserved?** Pending post-edit review.

**Were high-risk surfaces touched? If yes, were they validated?** Yes; full A4 is required before final acceptance.

**Did any opposition finding require a patch change?** Pending.

**Did the work need a mode transition?** None currently.

**Was Agent 5 required for this review? Was it run?** Required by full A4; pending all opposers.

**Final Mode C decision:** Pending independent opposition and Agent 5 synthesis.

**Reason:** The measured paths justify a narrow performance patch, but caching, cancellation, concurrency, and Windows Shell API changes require independent validation.
