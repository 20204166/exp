# Mode C - Safe Performance Improvement

## Purpose

Use Mode C for scoped performance improvements where behaviour must remain identical.

Mode C is correctness-first. A performance change is valid only if repo behaviour, public contracts, security/privacy boundaries, fail-closed behaviour, and user-facing output are preserved.

Mode C is not a rewrite mode, not a broad refactor mode, and not a feature-expansion mode.

## When to use

Use Mode C when the user asks to:

- improve performance
- speed up a slow function/path
- reduce memory use
- reduce repeated work
- reduce query count
- reduce startup/runtime overhead
- optimize a known hot path
- make validation faster
- improve build/test/runtime time

Do not use Mode C for broad rewrites, architecture redesign, feature work, speculative cleanup, or vague "make it better" edits.

## Mode transitions

Mode C can receive work from Mode A when a code-edit task is primarily performance-related.

Mode C must transition back to Mode A when the optimization introduces or exposes a correctness bug that must be repaired in the current patch.

Mode C must transition to Mode B when it discovers a suspected pre-existing bug outside the optimization scope. In that case, pause code changes and do not continue implementation unless the user approves.

Mode C final reports must include:

```text
Mode path:
Transition reasons:
Current final mode:
```

A mode transition does not reduce validation. The destination mode must complete its own gates.

## Required declaration

Every Mode C run starts with:

```text
BugGuard mode: Mode C - safe performance improvement
Target:
Performance symptom:
Allowed behaviour changes: none / explicitly listed
Risk level: low / medium / high / contradictory
Baseline evidence:
Correctness validation:
Performance validation:
Adversarial threshold: none / selective / full A4
Opposition file: not needed / created at docs/bug_hunts/performance_reviews/PERF-YYYYMMDD-NNN-opposition.md
Research pack use: main_auditor_research_pack.md default / research_link_pack.md deeper case / none needed
Reason:
```

## C1. Scope and baseline

Before editing, identify:

- exact target file/function/path
- caller/callee chain
- runtime entry point
- user-facing behaviour
- public contract
- tests that define current behaviour
- security/privacy/fail-closed boundaries
- data shape/order/filtering/permissions
- error/timeout/retry semantics
- logging/redaction expectations
- current performance symptom
- current baseline measurement, if feasible

If there is no bottleneck evidence, do not invent one. Ask for a target or perform read-only discovery first.

## C2. Bottleneck evidence

Prefer repo-local evidence:

- profiler output if already available
- repeated query/log evidence
- slow test/runtime output
- obvious repeated computation in confirmed hot path
- LR/drift/performance warning
- user-provided timing
- targeted local timing command

Grep-only is not bottleneck proof. A suspicious pattern is only a lead.

Do not optimize a path only because it "looks inefficient" unless the path is reachable and the change can be proven safe.

## C3. Safe optimization patterns

Allowed only when behaviour is preserved:

- remove duplicated work inside one request/task
- avoid repeated parsing/serialization when output is identical
- narrow expensive loops without changing result set
- memoize pure local computation with bounded scope
- replace obviously inefficient local data structure with equivalent one
- reduce DB query count while preserving filtering, ordering, permissions, and eager/lazy semantics
- avoid unnecessary file reads when cache invalidation is clear
- reduce logging overhead without reducing required observability/redaction
- make tests faster without reducing coverage or changing assertions

## C4. High-risk optimization patterns

Treat as high-risk and require stronger validation/adversarial review:

- caching across users, sessions, tenants, permissions, requests, tasks, or processes
- concurrency, parallelism, async scheduling, locking, or batching changes
- DB query rewrites, joins, pagination, ordering, filtering, or transaction changes
- retry/backoff/timeout/sleep removal
- browser automation timing/selector/navigation changes
- provider/API call reduction
- evidence/OCR/PDF/storage path changes
- auth/session/admin/security/privacy/redaction changes
- Celery/Redis/job idempotency changes
- native/Rust/frontend/build changes
- startup/import side effects
- lazy loading that changes failure timing

## C5. Correctness-first edit rule

Make the smallest change that addresses the measured bottleneck.

Do not:

- broaden scope
- rewrite architecture
- remove validation
- weaken security
- change public behaviour
- change tests to fit the optimization
- hide errors
- turn exceptions into silent fallbacks
- remove waits/retries without proving the contract
- change ordering/filtering/permissions/result shape to gain speed
- add cache without a safe invalidation/key/privacy story

## C6. Validation order

Run correctness validation before performance validation.

Required order:

1. `git diff --stat`
2. `git diff --check`
3. focused correctness tests for affected behaviour
4. relevant static/type checks for changed language surface
5. targeted performance comparison
6. relevant LR/drift checks if repo evidence requires them
7. adversarial review if high-risk or contradictory

A faster broken path is a failure.

If correctness validation fails, stop and fix correctness before measuring performance.

## C7. Performance comparison

Use the smallest honest measurement available:

```text
Before:
Command:
Input/fixture:
Result:
Notes:

After:
Command:
Input/fixture:
Result:
Notes:

Conclusion:
```

If before/after timings are noisy, report them as noisy. Do not claim performance improved unless the evidence supports it.

For microbenchmarks:

- keep input realistic
- avoid benchmarking only mocked code unless the real path is impossible
- run enough repetitions to reduce noise
- report environment caveats
- do not optimize for synthetic data at the expense of real behaviour

## C8. Cache safety checklist

Before adding or changing a cache, answer:

- What is the cache key?
- What invalidates it?
- Can it cross users, tenants, sessions, permissions, or requests?
- Can it leak private data?
- Can it serve stale security/evidence/payment/provider data?
- Is it bounded?
- What happens on error?
- Is it safe under concurrency?
- Is it safe across process restarts?
- What test proves this?

If these cannot be answered, do not add the cache.

## C9. DB/query safety checklist

Before changing DB queries, answer:

- Is the result set identical?
- Is ordering identical?
- Are filters identical?
- Are permissions identical?
- Are joins changing duplicates?
- Is pagination affected?
- Are lazy/eager loading semantics affected?
- Are transactions/flush/commit/rollback semantics preserved?
- Does SQLite/Postgres behaviour differ?
- What test proves this?

## C10. Async/job safety checklist

Before changing async/job behaviour, answer:

- Is ordering important?
- Is the operation idempotent?
- What happens on partial failure?
- What happens on retry?
- What happens on timeout?
- Can duplicate jobs happen?
- Can events be dropped?
- Is failure still visible?
- What test proves this?

## C11. Browser/provider safety checklist

Before optimizing browser/provider flows, answer:

- Does user-review still happen?
- Are CAPTCHA/2FA/final-submit boundaries preserved?
- Are waits tied to actual page state instead of arbitrary sleeps?
- Are provider-specific selectors/contracts preserved?
- Are ambiguous fields still surfaced to the user?
- Are retries and error reporting preserved?
- What test proves this?

## C12. Research pack use

Mode C has access to both research packs, but they are not equal.

Use `main_auditor_research_pack.md` by default for safe optimization semantics.

Use it for:

- Python performance-sensitive semantics
- pytest benchmark/test design
- basic static/type/tooling semantics
- FastAPI/Starlette response or middleware behaviour
- ordinary test design
- ordinary validation command choice
- deciding whether deeper research is needed

Use `research_link_pack.md` only for deeper cases, including:

- SQLAlchemy query/loading/transaction semantics
- Playwright waits, locators, navigation, browser timing, downloads, uploads
- Celery retries, idempotency, worker/broker behaviour
- Rust/native/PyO3/maturin/Cargo/rustfmt semantics
- security/cache/privacy/redaction/auth/session/CSRF/CORS issues
- provider docs or external API semantics
- framework/library behaviour that could prove or disprove optimization safety
- cases where the focused pack says escalation/deeper docs are needed

Do not make the main auditor read `research_link_pack.md` for every Mode C task.

Do not use broad web research by default. Official docs first.

Repo truth still wins. External docs can explain semantics, but current repo code/tests/runtime output must prove repo behaviour.

Before using external research, state:

```text
Research question:
Repo evidence that triggered it:
Pack used: main_auditor_research_pack.md / research_link_pack.md
Why this pack is enough:
How the answer could change the patch, test, or validation:
```

After research, record:

```text
Finding:
Repo-specific implication:
Local evidence still needed:
```

## C13. Adversarial review threshold

Use selective or full A4 when:

- high-risk optimization pattern is used
- correctness evidence is incomplete
- performance evidence contradicts correctness evidence
- caching/concurrency/DB/provider/browser/security boundaries are touched
- static checks/tests disagree
- main auditor is unsure

Agent 5 is required for full A4 according to `mode_a_patch_review.md`.

When escalating to selective or full A4, create the Mode C opposition file at `docs/bug_hunts/performance_reviews/PERF-YYYYMMDD-NNN-opposition.md` using `mode_c_opposition_template.md` (see the "Mode C opposition file" section below).

If unsure, escalate instead of guessing.

## Mode C opposition file

When Mode C escalates to selective or full A4 adversarial review, create a Mode C opposition file using `mode_c_opposition_template.md`.

Use path:

```text
docs/bug_hunts/performance_reviews/PERF-YYYYMMDD-NNN-opposition.md
```

If the repo already has an explicit performance-review folder convention, use that instead.

The opposition file must capture:
- main auditor performance claim
- before/after measurement evidence
- correctness validation evidence
- selected opposer findings
- Agent 5 audit when full A4 is used
- main auditor final synthesis

## Artifact ownership

The Mode C opposition artifact is the source of truth for adversarial review.

- The main auditor owns the scaffold, candidate summary, evidence index, and final synthesis.
- The main auditor may create the Mode C opposition file, fill the header, write the optimization claim, before/after measurement evidence, correctness validation evidence, and high-risk surface checklist.
- Each selected Opposer owns only its own Opposer section and must write that section directly into the Mode C opposition file.
- Agent 5, when required, owns only the Agent 5 evidence audit section and must write it directly into the Mode C opposition file.
- The main auditor must not fill Opposer 1/2/3/4 sections itself.
- Reviewer and Agent 5 sections must not be backfilled by the main auditor.
- General AI output is not a substitute for writing the required section into the review/opposition artifact.
- If a selected Opposer or Agent 5 cannot write its required section into the artifact, the review is incomplete and must be reported as incomplete instead of treating the reviewer as complete.
- For Mode C, the required selected Opposer sections in the Mode C opposition file must exist before Agent 5 or main auditor final synthesis can treat performance opposition as complete.

## Artifact write enforcement

Reviewer-owned sections must be authored directly by the assigned reviewer in the artifact.

The main auditor must not write, paste, transcribe, summarize, or backfill reviewer-owned sections or Agent 5 sections.

General AI output, terminal output, chat output, or copied reviewer text does not satisfy the artifact requirement.

If the selected reviewer cannot write directly to its required artifact section, the review is incomplete. The main auditor must report an orchestration/tooling gap instead of treating the reviewer as complete.

The main auditor may reference incomplete external reviewer output only as non-authoritative context, not as a completed reviewer section.

Final synthesis may begin only after all required reviewer-owned artifact sections exist.

For Mode C, selected performance Opposer sections must be written directly into the Mode C opposition file by the assigned Opposer. The main auditor must not capture or paste Opposer output into these sections.

Mode C opposition files are patch-review artifacts, not bug ledgers. Do not write Mode C performance candidates into `bugs_found_N.md` unless the work transitions to Mode B and validates a bug.

## C14. Final report

Report:

```text
BugGuard mode: Mode C - safe performance improvement
Target:
Performance symptom:
Mode C opposition file:
Files changed:
Behaviour preserved:
Public contracts preserved:
Security/privacy/fail-closed preserved:
Optimization made:
Baseline evidence:
Correctness validation:
Performance validation:
Before/after result:
Research pack used:
Adversarial review:
Commands run:
Commands not run and why:
Remaining risk:
Next safest validation:
```
