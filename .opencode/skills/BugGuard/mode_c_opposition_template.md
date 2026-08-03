# Mode C Opposition Template

Use this template for BugGuard Mode C adversarial review.

Mode C opposition validates a performance patch. It does not validate a bug candidate.

## Artifact ownership

The Mode C opposition artifact is the source of truth for adversarial review.

- The main auditor owns the scaffold, candidate summary, evidence index, and final synthesis.
- Each selected Opposer owns only its own Opposer section and must write that section directly into the artifact.
- Agent 5, when required, owns only the Agent 5 evidence audit section and must write it directly into the artifact.
- The main auditor must not fill reviewer-owned sections.
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

The question is:

```text
Is this performance patch safe, behaviour-preserving, and honestly measured?
```

## Header

```text
Mode C review ID: PERF-YYYYMMDD-NNN
Patch/review file:
Opposition file:
Mode path:
Target:
Performance symptom:
Allowed behaviour changes:
Files changed:
Baseline evidence:
Correctness validation:
Performance validation:
Research pack used:
Adversarial threshold:
```

## Main auditor candidate summary

**Optimization made:**

**Claimed performance win:**

**Before measurement:**

**After measurement:**

**Correctness evidence:**

**Public contracts that must remain unchanged:**

**Security/privacy/fail-closed boundaries:**

**High-risk surfaces touched:**
- cache: yes/no
- DB/query/session: yes/no
- async/job/retry/idempotency: yes/no
- browser/provider: yes/no
- auth/session/CSRF/CORS/admin: yes/no
- logging/redaction/privacy: yes/no
- OCR/evidence integrity: yes/no
- CSV/export exact output: yes/no
- settings/runtime config: yes/no
- template/static output: yes/no
- native/Rust/frontend/build: yes/no

**Mode transition history:**

```text
Mode path:
Transition reasons:
Current final mode:
```

---

## Opposer 1 — Reproduction and measurement skeptic

**Goal:** Prove the claimed speedup is not real, not measured correctly, or not tied to the real path.

**Different angle required:** reproduce before/after measurements, check noise, fixtures, warm/cold process effects, mocked-vs-real path, command validity.

**Questions:**
- Does the benchmark measure the real hot path?
- Was correctness validated before performance claims?
- Are before/after measurements comparable?
- Is the timing noisy, warmed, cached, or process-order dependent?
- Does the patch optimize synthetic data instead of real repo behaviour?
- Is the improvement meaningful enough to justify the risk?

**Repo evidence checked:**

**Commands run:**

**Measurement challenge:**

```text
Command:
Input/fixture:
Result:
Interpretation:
```

**Verdict:** Safe / Weak evidence / Unsafe / Needs more evidence

---

## Opposer 2 — Repo-truth and contract skeptic

**Goal:** Prove the patch changed repo behaviour, public contracts, monkeypatch surfaces, tests, route/task names, data shape, or hidden-test-sensitive semantics.

**Different angle required:** exact repo contracts, existing tests, public names, caller/callee chain, fixtures, monkeypatch surfaces.

**Questions:**
- Did any public name/signature/task/route/payload/status code change?
- Did monkeypatch surfaces remain compatible?
- Did data shape, ordering, filtering, permissions, or row/file output change?
- Did the patch preserve existing tests and hidden-test-sensitive behaviour?
- Did the patch rely on assumptions not proven by repo code/tests?

**Repo evidence checked:**

**Commands run:**

**Contract challenge:**

```text
Contract:
Evidence before:
Evidence after:
Risk:
```

**Verdict:** Safe / Weak evidence / Unsafe / Needs more evidence

---

## Opposer 3 — Architecture, security, and failure-mode skeptic

**Goal:** Prove the patch weakens architecture, security, privacy, fail-closed behaviour, error timing, concurrency, retry/idempotency, DB/session lifecycle, or evidence integrity.

**Different angle required:** security/privacy boundaries, failure paths, transaction boundaries, concurrency/cache safety, retry/idempotency.

**Questions:**
- Did failure move from startup/import to runtime in a way that matters?
- Did the patch delay an error that should remain fail-fast?
- Did it affect auth/session/CSRF/CORS/admin/rate-limit behaviour?
- Did it affect token handling, redaction, privacy, logs, or user data?
- Did it affect retry, timeout, idempotency, partial failure, or background job semantics?
- Did it add or change cache/concurrency behaviour safely?
- Did DB/session/transaction semantics remain unchanged?

**Repo evidence checked:**

**Commands run:**

**Failure-mode challenge:**

```text
Failure mode:
Before behaviour:
After behaviour:
Safety verdict:
```

**Verdict:** Safe / Weak evidence / Unsafe / Needs more evidence

---

## Opposer 4 — External semantics and docs skeptic

**Goal:** Prove the patch misunderstands framework/library/provider/tool semantics.

**Different angle required:** official docs only unless unavailable; use focused research only for semantics that affect the patch.

**Use research only if needed for:**
- SQLAlchemy query/session/loading semantics
- FastAPI/Starlette middleware/static/template behaviour
- Playwright/browser waits/provider behaviour
- Celery retry/idempotency/task semantics
- Python import/logging/csv/timeit/profile semantics
- security/cache/privacy/provider documentation
- Rust/native/frontend/build tooling if touched

**Research question:**

```text
Research question:
Repo evidence that triggered it:
Pack used: main_auditor_research_pack.md / research_link_pack.md
Why this pack is enough:
How the answer could change the patch, test, or validation:
```

**External docs used:**

**Repo-specific implication:**

**Local evidence still needed:**

**Verdict:** Safe / Weak evidence / Unsafe / Needs more evidence

---

## Agent 5 — Mode C Superpower Evidence Auditor

Agent 5 is **not** required for every Mode C adversarial review. Agent 5 runs only when one of the following is true:

- full A4 is selected for this Mode C review, or
- the selected Mode C threshold or repo policy explicitly requires Agent 5.

Agent 5 is required only when the header's `Adversarial threshold:` field is `full A4`, or when a selective threshold explicitly requires Agent 5 under this review's declared policy. Selective thresholds do not require Agent 5 by default.

Selective Mode C opposition may use only the selected independent reviewers and may omit Agent 5 entirely. Do not imply Agent 5 always runs. Do not simulate Agent 5 when it is not required.

When a registered reviewer or required Agent 5 is unavailable, use the portable independent-review fallback in `SKILL.md`. The main auditor must not substitute its own review, and incomplete independent review remains incomplete.

When Agent 5 is required, it starts only after all required opposing sections are complete. It must use a registered or fallback independent subagent; never simulate the Agent 5 audit.

When Agent 5 runs, it must read:
- main auditor candidate summary
- diff summary
- before/after measurements
- correctness validation
- all required opposing sections
- command outputs
- relevant repo files/tests
- research notes if used

Agent 5 must not invent missing evidence.

When Agent 5 is not required for this review, leave the section below marked `Not run for this review` with the reason and do not fabricate Agent 5 findings.

## Agent 5 evidence audit

**Threshold declared in header:** none / selective / full A4

**Agent 5 required by this threshold:** yes / no

**Reasoning:**

**Agent 5 run for this review:** yes / no

**Reason Agent 5 was/was-not run:**

**Evidence completeness:**

**Correctness-before-speed check:**

**Performance measurement check:**

**Contract preservation check:**

**Security/privacy/fail-closed check:**

**Failure timing check:**

**High-risk surface check:**

**Mode transition check:**

**Missing evidence:**

**Blocking issues:**

**Non-blocking issues:**

**Agent 5 final verdict:** Safe to accept / Unsafe / Needs more evidence / Transition required / Not run for this review

---

## Test and measurement evidence synthesis

| Evidence | Path/command | What it tested/measured | Result | Supports patch | Challenges patch | Gaps |
|---|---|---|---|---|---|---|
| Correctness tests | | | pass/fail/error/timeout | | | |
| Static/type checks | | | pass/fail/error/timeout | | | |
| Before measurement | | | | | | |
| After measurement | | | | | | |
| Opposer 1 challenge | | | | | | |
| Opposer 2 challenge | | | | | | |
| Opposer 3 challenge | | | | | | |
| Opposer 4 challenge | | | | | | |
| Agent 5 audit | not run / path | | | | | |

The main auditor must decide from this table, not from vibes.

---

## Main auditor final synthesis

**Did correctness validation pass before performance claims?**

**Is the before/after comparison honest?**

**Was the real hot path measured?**

**Were public contracts preserved?**

**Were security/privacy/fail-closed boundaries preserved?**

**Were high-risk surfaces touched? If yes, were they validated?**

**Did any opposition finding require a patch change?**

**Did the work need a mode transition?**

**Was Agent 5 required for this review? Was it run?**

**Final Mode C decision:** Accept patch / Reject patch / Needs more evidence / Transition to Mode A / Transition to Mode B

**Reason:**

---

## Final report fields

```text
BugGuard mode: Mode C — safe performance improvement
Mode C review ID:
Mode path:
Transition reasons:
Current final mode:
Target:
Performance symptom:
Files changed:
Behaviour preserved:
Public contracts preserved:
Security/privacy/fail-closed preserved:
High-risk surfaces touched:
Optimization made:
Baseline evidence:
Correctness validation:
Performance validation:
Before/after result:
Opposition file:
Agent 5 verdict:
Research pack used:
Commands run:
Commands not run and why:
Remaining risk:
Follow-up Mode C candidates:
Next safest validation:
```
