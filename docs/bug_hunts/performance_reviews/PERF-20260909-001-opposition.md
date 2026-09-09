# PERF-20260909-001 - Mode C Opposition

```text
Mode C review ID: PERF-20260909-001
Patch/review file: maintenance/components/downloads.py
Opposition file: docs/bug_hunts/performance_reviews/PERF-20260909-001-opposition.md
Mode path: C
Target: DownloadScanner._download_file_stats
Performance symptom: repeated Path.stat and path parsing dominate Downloads scans
Allowed behaviour changes: none
Files changed: maintenance/components/downloads.py
Baseline evidence: native 30-repetition audit plus cProfile on the current Downloads tree
Correctness validation: focused Downloads, scanner, and storage tests passed before review
Performance validation: interleaved 30-round old/new metadata comparison
Research pack used: main_auditor_research_pack.md default
Adversarial threshold: full A4 (fallback Opposers 1-4 and Agent 5)
```

## Main Auditor Candidate Summary

**Optimization made:**

`_download_file_stats` now uses the already-yielded `os.DirEntry.stat(follow_symlinks=False)` rather than constructing a `Path` and issuing a second `Path.stat()` call. Directory traversal, symlink filtering, error handling, result keys, and downstream hashing remain unchanged.

**Claimed performance win:**

The direct metadata phase improved from median `78.6ms`, p95 `93.6ms` to median `56.1ms`, p95 `69.6ms` in an interleaved 30-round comparison on the same Downloads tree. The full scan baseline remains separately recorded because hashing and candidate analysis vary with cache state.

**Public contracts that must remain unchanged:**

- Non-dot files are returned with the same `Path` keys.
- Symlinked files and directories are excluded.
- `stat` failures remain fail-soft.
- File size, mtime, device, inode, duplicate grouping, ordering, progress, and cancellation semantics remain unchanged.
- No cleanup action is performed by scanning.

**High-risk surfaces touched:**

- cache: no
- DB/query/session: no
- async/job/retry/idempotency: no
- browser/provider: no
- auth/session/CSRF/CORS/admin: no
- logging/redaction/privacy: no
- OCR/evidence integrity: no
- CSV/export exact output: no
- settings/runtime config: no
- template/static output: no
- native/Rust/frontend/build: no

## Opposer 1 - Reproduction And Measurement Skeptic

**Repo evidence checked:**

- `maintenance/components/downloads.py:277-310` is the measured metadata path. The patch changes one call from `Path.stat()` to `DirEntry.stat(follow_symlinks=False)` after `walk_directory_entries()` has already yielded the entry.
- `maintenance/components/scan_support.py:177-227` shows the shared walker performs `os.scandir`, non-following directory/file checks, hidden-name filtering, and yields the same `DirEntry` used by the patched call.
- `tests/test_components.py:126-205`, `tests/test_storage_conservative.py:13-76,112-164`, and `tests/test_maintenance.py:1130-1194` cover duplicate results, cache behaviour, cancellation, hidden files, symlinks, and stat values, but do not contain a before/after timing test.
- `docs/performance/scanner-performance.json:1102-1234` records full `downloads` scans, not an isolated metadata phase. Its warm samples are approximately `208-260ms`, so they cannot independently establish the claimed `56.1ms` metadata result.
- The current diff for the target is exactly one application line (`1 insertion, 1 deletion`); unrelated worktree changes were not used as evidence.

**Commands run:**

- `python -m unittest tests.test_components.DownloadScannerTests tests.test_storage_conservative tests.test_maintenance.SharedWalkDirectoryTests -v` -> 25 tests passed.
- `ruff check .` -> passed.
- `ruff format --check .` -> passed (`325 files already formatted`).
- `pyright maintenance/components/downloads.py maintenance/components/scan_support.py tests/test_components.py tests/test_maintenance.py tests/test_storage_conservative.py` -> 0 errors.
- `mypy --ignore-missing-imports maintenance/components/downloads.py maintenance/components/scan_support.py tests/test_components.py tests/test_maintenance.py tests/test_storage_conservative.py` -> success, 5 source files.
- `pyright` repo-wide -> failed on pre-existing/generated `build/lib/maintenance/components/temperature.py` duplicate-module diagnostics; no target-file diagnostic.
- `mypy --ignore-missing-imports` repo-wide -> usage error because no target was supplied; this is not treated as a pass.
- An inline Python benchmark (no counter-test file created) implemented the pre-patch loop with `path.stat()` and the post-patch loop via `DownloadScanner._download_file_stats`, interleaved 30 rounds, compared complete `os.stat_result` dictionaries, and ran one `cProfile` pass for each implementation.

**Measurement challenge:**

```text
Command:
  Inline `python - <<'PY'` benchmark using `walk_directory_entries(...,
  skip_dotfiles=True)`, old `Path.stat()` implementation, current
  `DirEntry.stat(follow_symlinks=False)` implementation, 30 interleaved
  repetitions, and cProfile. A second run reversed the per-round order.

Input/fixture:
  Controlled temporary tree: 1,200 visible files in 12 directories plus one
  hidden directory/file. Real local `/home/btn17/Downloads`: 2,768 yielded
  files. Both implementations used the same walker and fixture; no hashing or
  candidate analysis was included because the claim is for metadata only.

Result:
  Controlled tree, old-first: old median 20.999ms, p95 22.489ms; new median
  20.725ms, p95 31.152ms; 1.01x median speedup. Both output dictionaries were
  equal. Real tree, old-first: old 56.878ms median / 74.574ms p95; new
  54.199ms / 71.249ms; 1.05x. Reversed order: old 66.061ms / 81.300ms;
  new 65.895ms / 89.810ms. A separate old-first run was old 57.929ms /
  73.140ms versus new 55.662ms / 75.578ms. All output dictionaries were
  equal.

  cProfile on the controlled tree attributed old `pathlib.Path.stat` to
  25.330ms across 1,200 calls and the underlying `posix.stat` to 24.832ms;
  new `DirEntry.stat` took 4.960ms across 1,200 calls. The complete old/new
  wrapper timings were 45.303ms and 40.587ms respectively. This supports the
  hot-call attribution, but not a stable end-to-end percentage.

Interpretation:
  The patch does remove the extra Path construction/stat route and is tied to
  the real metadata hot path. However, the controlled fixture shows almost no
  wall-clock gain, and real-tree medians shift materially with whether old or
  new runs first. The observed real-tree gain is only about 2-5%, substantially
  below the opposition brief's claimed median change (78.6ms to 56.1ms,
  about 29%). The JSON performance record does not provide the isolated
  before/after samples needed to reconcile that discrepancy. The unchanged
  output comparison and focused correctness/static checks support safety, but
  the benchmark evidence is not sufficiently reproducible to validate the
  claimed magnitude.
```

**Verdict:** Needs more evidence. The one-line optimization is plausibly safe and the profile confirms the intended syscall reduction, but Opposer 1 cannot independently reproduce the stated metadata speedup. Accepting the patch should be conditional on publishing the exact benchmark command, fixture/tree identity, raw paired samples, and an attribution that separates metadata collection from hashing and candidate analysis. No counter-test was used, so there is no counter-test hygiene exception to report.

## Opposer 2 - Repo-Truth And Contract Skeptic

**Repo evidence checked:**

- `maintenance/components/downloads.py:207-275` keeps the public `DownloadScanner.scan_downloads(progress_callback, cancel_event) -> list[FileCandidate]` signature, performs the same cancellation checks, builds the same `FileCandidate` fields, and applies the same final sort by descending size and case-folded/original path.
- `maintenance/components/downloads.py:277-310` still returns `dict[Path, os.stat_result]`; the only changed operation is the value acquisition at line 293. The `Path(entry.path)` key is unchanged, and the existing `OSError`/`ValueError` fail-soft boundary remains around the stat call.
- `maintenance/components/scan_support.py:177-227` is the exact producer contract: `walk_directory_entries` yields `os.DirEntry`, prunes dotfiles when requested, does not descend into symlinked directories, and yields only `entry.is_file(follow_symlinks=False)` entries. It checks cancellation before each entry and closes each scandir handle.
- `maintenance/scanner.py:159-207,1624-1644,1700-1729` shows the facade/caller chain. `SystemScanner.scan_downloads` delegates to the component scanner, synchronizes thresholds and the existing hash/marker/cancellation seams, and retains the historical private `_download_file_stats` adapter. `algo.py:94-105` exposes the storage-candidate result without reshaping it.
- `maintenance/models.py:89-94` defines the unchanged four-field frozen `FileCandidate` result shape. `tests/test_components.py:126-205`, `tests/test_maintenance.py:36-235,1130-1194`, and `tests/test_storage_conservative.py:13-76,112-164,166-200` assert duplicate selection, stable ordering, hidden-path and symlink exclusion, stat sizes, cache invalidation/rechecks, progress, cancellation, and fail-soft traversal.

**Commands run:**

- `git diff -- maintenance/components/downloads.py` -> one-line implementation change only: `path.stat()` replaced by `entry.stat(follow_symlinks=False)`.
- `git diff --check` -> passed.
- `python -m unittest tests.test_components.DownloadScannerTests tests.test_storage_conservative tests.test_maintenance.ScannerTests tests.test_maintenance.SharedWalkDirectoryTests -v` -> 85 tests passed.
- `grep` searches over `maintenance`, `algo.py`, and `tests` for `scan_downloads`, `_download_file_stats`, `DownloadScanner`, `_cached_file_hash`, and related seams -> no public caller expects a changed result shape; callers consume `FileCandidate` lists or the private stats mapping.

**Contract challenge:**

```text
Contract: A scan returns the same Path-keyed os.stat_result data and downstream
FileCandidate values; stable files, symlinks, ordering, progress, cancellation,
hash-cache identity, and fail-soft errors must not change.
Evidence before: The old call was Path(entry.path).stat(), which follows a
symlink if the directory entry is replaced after the walker's non-following
is_file check. The same Path key and stat result fed large-file grouping,
duplicate grouping, and _prune_hash_cache/_cached_file_hash.
Evidence after: For the normal entries guaranteed by
walk_directory_entries(..., follow_symlinks=False), DirEntry.stat(False)
returns the regular file metadata consumed by the same downstream code. The
new call preserves the dict key, stat fields used by stat_fingerprint
(size/mtime/ctime/device/inode), exception handling, progress counts, and all
cancellation checks. Final candidate ordering is explicitly re-sorted, and
duplicate keeper ordering is independently path-sorted.
Risk: A private monkeypatch or hidden fixture that supplies a path-only fake
entry to _download_file_stats would now fail with AttributeError; the exact
repo walker contract supplies os.DirEntry and the named tests use real entries
(the iterator-error test fails before yielding an entry). A concurrent
replace-with-symlink race also has different metadata semantics, but the new
non-following stat is more conservative and the stable symlink contract is
already enforced by the shared walker. No evidence shows a public caller or
persisted consumer relying on the old follow-symlink behavior.
```

The stat fingerprint/cache path is not bypassed: `_prune_hash_cache` still
receives the same mapping, and `_cached_file_hash` still validates the
fingerprint plus full-content marker before reuse. Hash failures remain
`OSError`-skipped in `_mark_duplicate_downloads`; the patch does not alter
progress message cadence or cancellation propagation.

**Verdict:** Safe. Repo contracts and all named correctness tests support
behavior preservation for the real `DirEntry` producer. The only identified
concern is private-test monkeypatch compatibility with unrealistic path-only
entry fakes, which is not a confirmed application regression. The measured
speedup magnitude remains Opposer 1's separate evidence gap; this review finds
no contract reason to reject the one-line optimization.

## Opposer 3 - Architecture, Security, And Failure-Mode Skeptic

**Repo evidence checked:**

- `maintenance/components/downloads.py:207-245,277-310` keeps the per-scanner `_downloads_scan_lock` around the complete scan, preserves the existing cancellation checks, and catches `(OSError, ValueError)` around metadata collection. The patch changes no lock, retry, callback, or logging path.
- `maintenance/components/scan_support.py:177-227` is the producer boundary. It uses `os.scandir`, tests directories and files with `follow_symlinks=False`, skips dotfiles, closes each iterator in `finally`, tolerates traversal `OSError`, and lets `ScanCancelled` propagate.
- `maintenance/components/downloads.py:471-544` keeps hash-cache access under `_hash_cache_lock`; cache fingerprints, content markers, and post-hash `Path.stat()` checks are unchanged. The optimization is not a cache or concurrency redesign.
- `maintenance/actions.py:236-299` is the separate destructive boundary. `FileManager` rejects direct symlinks, resolves and rechecks the target under the allowed Downloads root, verifies device/inode before calling `send2trash`, and reports per-file failures without rolling back earlier moves.
- `tests/test_components.py:126-205`, `tests/test_storage_conservative.py:79-163,202-314`, and `tests/test_maintenance.py:1130-1228` cover read-only scanning, symlink exclusion, cancellation, stat values, cache invalidation, cleanup rejection, and partial cleanup failure. They do not force a replacement race between directory enumeration and metadata/hash/cleanup.

**Commands run:**

- `python -m unittest tests.test_components.DownloadScannerTests tests.test_storage_conservative tests.test_maintenance.SharedWalkDirectoryTests -v` -> 25 tests passed.
- `git diff -- maintenance/components/downloads.py maintenance/components/scan_support.py maintenance/scanner.py maintenance/actions.py` -> only the intended one-line `Path.stat()` to `DirEntry.stat(follow_symlinks=False)` change appears in the scoped implementation; unrelated worktree changes were not used as evidence.
- `git diff --check` -> passed as recorded by the preceding opposition evidence.
- `ruff check .`, `ruff format --check .`, and targeted `pyright`/`mypy` checks -> passed as recorded in Opposer 1; repo-wide `pyright` has unrelated generated duplicate-module diagnostics and repo-wide `mypy --ignore-missing-imports` was invoked without a target.

**Failure-mode challenge:**

```text
Failure mode: Entry disappears, becomes inaccessible, or metadata lookup fails.
Before behaviour: Path(entry.path).stat() performs a path-based, following stat;
an OSError or ValueError is caught and that entry is omitted. A replacement
symlink could instead cause the old call to observe the symlink target.
After behaviour: entry.stat(follow_symlinks=False) performs a non-following
DirEntry stat; the same exceptions are caught and the entry is omitted. A
replacement symlink is observed conservatively as the link (or the lookup can
fail), rather than being promoted to target-file metadata.
Safety verdict: Safe and security-conservative. This is a deliberate race
semantic difference, but it cannot cause the scanner itself to delete anything.
The cleanup boundary rechecks the submitted Path and rejects symlinks and
out-of-root targets before send2trash.

Failure mode: File changes after enumeration or DirEntry metadata is cached.
Before behaviour: Path.stat() obtains a fresh path-based snapshot at the call;
it can follow a newly installed symlink. Hashing later uses the Path and its
existing fingerprint/marker rechecks, so no atomic scan guarantee exists.
After behaviour: DirEntry.stat(False) can use the entry's non-following cached
metadata and can therefore describe an earlier entry state. Later hashing and
its existing Path.stat()/marker checks still validate content stability before
cache insertion or reuse; a changed file can be skipped after retry.
Safety verdict: Residual weak-consistency risk, not a confirmed regression.
Neither implementation provides an atomic snapshot. The new result is more
conservative for symlink replacement, while a stale size/mtime can affect
which files reach the hash stage during a concurrent mutation.

Failure mode: Cancellation, concurrent scans, or partial failures.
Before behaviour: Cancellation is checked by the shared walker and downstream
loops; the scan lock serializes calls; stat errors are fail-soft per entry;
hash errors are fail-soft per file; progress is emitted from the same count.
After behaviour: All of those boundaries are unchanged. `DirEntry.stat()` is
not a new blocking retry or worker operation, and its caught errors do not
abort the directory walk. The lock remains held until the complete scan exits,
including cancellation, and the hash-cache lock remains independent.
Safety verdict: Safe. No new partial-commit, retry, deadlock, or cancellation
window was introduced.

Failure mode: Logging, privacy, and cleanup separation.
Before behaviour: Stat failures are silently omitted; scanning returns Paths
and stats only, with no cleanup side effect. Destructive failures are reported
by FileManager after independent validation.
After behaviour: The same exception boundary and lack of stat logging remain;
no path or file contents are newly logged, and no cleanup call was added.
Safety verdict: Safe. Privacy and non-destructive scan contracts are preserved.
```

**Risks and limits:**

- The patch does not make enumeration, stat, hashing, or trashing atomic against another process. A hostile or merely active producer can still replace a path between phases; `FileManager` is the relevant fail-closed control for cleanup, not the scanner metadata choice.
- `DirEntry.stat(False)` is tied to the shared walker’s `os.DirEntry` contract. A private monkeypatch that yields path-only objects would fail with `AttributeError`, which is outside the repository producer contract and is not caught by the existing fail-soft boundary.
- The focused tests do not reproduce a live rename/replace race or verify stale `DirEntry` cache timing. That is a coverage gap, but no test or caller evidence shows an atomic-stat guarantee that the patch violates.
- Partial scan results are not published on cancellation or traversal failure: a cancellation propagates and an `OSError` for an individual entry is omitted, matching the old path-stat boundary. Cleanup partial-failure semantics are independently preserved by `FileManager` and are outside this patch.

**Verdict:** Safe with a bounded weak-consistency caveat. The change preserves architecture, lock ownership, cancellation propagation, fail-soft handling, logging/privacy behaviour, and the scan/cleanup separation. Non-following metadata removes a symlink-following race hazard rather than weakening path safety. The only material residual risk is that `DirEntry` metadata may be stale during concurrent file mutation, but the existing hash fingerprint/content validation and independent cleanup revalidation limit its impact. No architecture or security blocker is established; benchmark magnitude remains the separate evidence gap identified by Opposer 1.

## Opposer 4 - External Semantics And Docs Skeptic

**Research question:** Does `os.DirEntry.stat(follow_symlinks=False)` return metadata with the same fields and freshness/error/symlink semantics as the replaced `Path.stat()` call on every supported platform, or can those differences invalidate the optimization?

**Repo trigger:** `maintenance/components/downloads.py:286-295` now stores the non-following `DirEntry.stat()` result in the `dict[Path, os.stat_result]` consumed by duplicate selection and hashing. `maintenance/scan_support.py:177-223` deliberately yields real `os.DirEntry` objects after `is_file(follow_symlinks=False)`. The repository contract nevertheless requires unchanged size, mtime, device, inode, duplicate grouping, and cache behavior; `stat_fingerprint()` at `maintenance/components/scan_support.py:165-174` uses size, mtime, ctime, device, and inode.

**Source used:** Official Python `os` documentation only: [`os.DirEntry`](https://docs.python.org/3/library/os.html#os.DirEntry), [`DirEntry.stat()`](https://docs.python.org/3/library/os.html#os.DirEntry.stat), and [`os.stat_result`](https://docs.python.org/3/library/os.html#os.stat_result). The documentation states that `DirEntry.stat()` returns a `stat_result`, follows symlinks by default but not with `False`, caches separate results for each setting, can raise `OSError`, and on Windows sets `st_ino`, `st_dev`, and `st_nlink` to zero; it directs callers needing those Windows fields to use `os.stat()`. No non-official source was used.

**Semantics challenge:**

- The documented Windows behavior is a direct contract concern, not merely a benchmark caveat. The old `Path(entry.path).stat()` follows the path and can provide device/inode values; the new non-following `DirEntry.stat(False)` may provide zero `st_dev` and `st_ino`. That changes the repository's fingerprint inputs and can change hash-cache retention/revalidation behavior, even though full-content markers reduce the chance of an incorrect digest reuse.
- The docs explicitly say the `DirEntry` stat result is cached and recommend `os.stat(entry.path)` for up-to-date information. The old call performed a path stat at the metadata phase; the new call can return metadata from the directory-entry cache. This matters under mutation between enumeration and stat, and is not equivalent freshness semantics.
- `follow_symlinks=False` correctly returns link metadata rather than target metadata. The shared walker excludes symlinks as observed during `is_file(False)`, but a replacement race can make a previously yielded entry a symlink. The new code then records link metadata; the old following `Path.stat()` could record target metadata. Both calls may raise `OSError` for disappearance or access failure, and the existing `(OSError, ValueError)` boundary remains appropriate, but it does not erase this race-level result difference.
- The documentation's Windows reparse-point behavior means `False` covers name-surrogate reparse points such as symlinks and junctions, with additional platform-specific handling for unresolved points. The repository has no Windows evidence showing that this produces the same `stat_result` fields or candidate/cache behavior as the old call.

**Local evidence needed:** A Windows run, or an equivalent supported CI job, must compare old and new `stat_result` fields for ordinary files, symlinks, junctions/reparse points, and files changed or removed after `scandir()`; it must include `st_size`, timestamps, `st_dev`, `st_ino`, and the fingerprints used by the cache. The existing Linux probe is insufficient: on Python 3.12.3/Linux, ordinary-file fields matched, but a previously statted `DirEntry` returned its cached result after the file was unlinked, confirming that freshness cannot be assumed. A Windows result is also needed for missing/inaccessible entries to verify the fail-soft omission path across the supported filesystem implementations.

**Verdict:** **Needs more evidence; not safe to sign off as a cross-platform behavior-preserving optimization.** Official semantics identify a concrete Windows device/inode contract mismatch and a documented cached-result freshness difference. On this Linux host the ordinary-file result matched and the existing error boundary is plausible, but that local result cannot disprove the Windows field difference or concurrent-mutation behavior. Until Windows field/cache evidence is supplied, the claimed optimization should be treated as conditionally safe on the tested POSIX path, not safe for the repository's declared platform-independent contract.

## Agent 5 - Mode C Superpower Evidence Auditor

**Threshold declared in header:** selective. The user-designated review is full A4, so this Agent 5 audit is required despite the stale header value.

**Agent 5 required by this threshold:** yes

**Reasoning:** All four Opposer sections are present, and the review request explicitly escalates this packet to full-A4 evidence auditing. This section is an independent fallback audit because the registered `bugguard-agent5` is unavailable.

**Agent 5 run for this review:** yes

**Reason Agent 5 was/was-not run:** Run against the complete opposition artifact, the target diff, the cited implementation/tests/reports, and fresh focused validation commands. No application code or tests were changed.

**Evidence completeness:** The implementation scope is verifiable: `maintenance/components/downloads.py` has exactly one changed line, replacing `Path.stat()` with `DirEntry.stat(follow_symlinks=False)`. The shared walker and downstream cache/hash paths are readable and the focused correctness evidence is coherent. The isolated before/after benchmark is not durable repo evidence: its exact command, raw paired samples, environment details, and profile files are absent. The checked-in JSON/Markdown report measures complete Downloads scans, not the isolated metadata phase claimed in the summary.

**Correctness-before-speed check:** Supported for the recorded focused run: 85 relevant tests passed, followed by target-scope Pyright (0 errors) and Mypy (success), with Ruff check/format and diff check passing. The evidence does not establish that a full repository test/static gate passed; repo-wide Pyright has pre-existing generated duplicate-module diagnostics and the recorded repo-wide Mypy invocation had no target and therefore was a usage error. No counter-test was created, despite the design document requiring one for each implemented candidate.

**Performance measurement check:** The intended hot call is correctly attributed to the metadata loop, and the profile narrative supports removal of the `Path.stat()` route. However, the claimed `78.6ms` to `56.1ms` result is not reproducible from the persisted report and conflicts with the independently recorded controlled-tree result (about 1.01x median) and real-tree result (about 1.05x, order-sensitive). The evidence supports a plausible syscall/local-overhead reduction, not the claimed magnitude or a stable end-to-end gain. The full-scan report cannot repair that attribution gap because hashing and candidate analysis are included.

**Contract preservation check:** On the repository’s real `os.DirEntry` producer, keys, stat mapping shape, filtering, progress, cancellation, sorting, duplicate/hash-cache inputs, and fail-soft `OSError`/`ValueError` handling remain unchanged. The change does alter race-level semantics: non-following entry metadata can describe a replaced symlink or cached/stale directory-entry state, whereas the old path stat followed the current path. That is not proven to violate an application guarantee, but it is not behaviorally identical under concurrent mutation. A path-only private fake would also fail with `AttributeError`, outside the documented producer contract.

**Security/privacy/fail-closed check:** No cleanup, logging, permission, or public API boundary changed. The separate `FileManager` revalidation remains the destructive fail-closed control. Non-following stat is conservative for symlink replacement. No security blocker is evidenced, but the scanner’s metadata is not an atomic snapshot and this optimization must not be described as making the cleanup race-safe.

**Failure timing check:** Normal stat failures remain omitted within the same caught exception boundary; cancellation and traversal behavior are unchanged. The only material timing/observation change is the use of `DirEntry`’s potentially cached metadata and non-following symlink semantics. No evidence shows callers require fresh path-following metadata, but no race test proves the opposite cases are harmless.

**High-risk surface check:** No cache policy, concurrency primitive, database, provider, UI, or destructive action was changed. The stat result does feed the existing hash-cache fingerprint, so filesystem freshness and platform-specific `stat_result` fields are still relevant. Opposer 4’s official-document finding is unresolved: Windows `DirEntry.stat(False)` may provide zero device/inode fields and differs in documented caching/freshness behavior. No native Windows or supported CI evidence was supplied.

**Mode transition check:** No Mode A or Mode B transition is required from the evidence reviewed. The Windows/freshness issue is an unresolved cross-platform contract question within this optimization, not a confirmed bug or a separately validated pre-existing defect.

**Missing evidence:**

- Exact reproducible benchmark command and persisted raw paired samples/profile output.
- A fresh comparison tying metadata-only timing to the claimed numbers and separating it from full scan/hash/candidate costs.
- Native Windows evidence for ordinary files, symlink/junction/reparse-point handling, `st_size`, timestamps, `st_dev`, `st_ino`, fingerprints, and failure omission.
- Evidence for mutation/removal between enumeration and stat, including cached `DirEntry` metadata behavior.
- The required candidate-specific counter-test.
- A valid repo-wide Mypy run and a clean explanation or remediation for the repo-wide Pyright generated-tree diagnostic.

**Blocking issues:** Cross-platform behavior-preservation is not established because the changed stat fields feed cache fingerprints and no Windows evidence exists. The headline performance claim is also unsupported by durable, reproducible measurements. These block unconditional acceptance, but they do not prove the one-line implementation is unsafe on the tested POSIX path.

**Non-blocking issues:** The focused static/test gates pass; the implementation is narrow; the profile attribution is directionally credible; and the cleanup boundary remains independent. The missing counter-test is a process/design nonconformance and should be closed before treating the candidate as fully evidenced.

**Agent 5 final verdict:** **Needs more evidence.** Conditionally retainable for the tested Linux/POSIX path as a low-risk optimization, but not safe to accept as a repository-wide behavior-preserving change and not supported at the claimed performance magnitude until the missing benchmark artifacts and native Windows/freshness evidence are supplied. No app-code change is recommended from this audit alone.

## Main Auditor Final Synthesis

**Evidence reconciliation:**

Opposer 2 and Opposer 3 found the one-line change narrow and safe on the real
POSIX `DirEntry` producer. Opposer 1 and Agent 5 found that the claimed
`78.6ms` to `56.1ms` metadata improvement is not reproducible from durable
artifacts; independent paired runs measured approximately 2-5% improvement
with order-sensitive p95 results. Opposer 4 identified an unresolved official
Python semantics issue: Windows `DirEntry.stat(False)` may produce different
device/inode fields and cached metadata, both of which feed this repository's
hash fingerprint path.

**Decision:**

Rejected for the current cross-platform application. The implementation has
been restored to `Path.stat()` because the required Windows and mutation-race
evidence is unavailable and the honest measured win does not justify the
cross-platform contract risk. The candidate remains a valid future
platform-specific investigation if native Windows evidence, a durable raw
benchmark artifact, and a counter-test are supplied.

**Mode path:** C

**Transition reasons:** no transition; candidate rejected within Mode C because
performance evidence was weak and behavior preservation was not established
across declared platforms.

**Current final mode:** C, candidate rejected; no optimization retained.
