# Mode B Main Auditor

This file is the threshold and synthesis guide for BugGuard Mode B.

## Scope

Use this file when selecting the Mode B threshold, deciding whether to escalate, or preparing the main-auditor synthesis pass before B8.

## Main auditor research pack

When evidence synthesis depends on framework/tool/language semantics, read [`main_auditor_research_pack.md`](./main_auditor_research_pack.md).

Use it to:

- refine the decisive question
- choose official docs to check
- improve PoC/counter-test design
- avoid inventing validation commands
- decide whether Agent 4 or Agent 5 escalation is needed

Do not turn this into broad web research. Research must answer a specific repo-triggered question.

## Bug spark discovery heuristics

A spark is not a bug. A spark is a lead worth investigating.

Before forming a BUG candidate, the main auditor should look for sparks that combine at least two evidence signals.

Strong sparks usually combine:

- suspicious code pattern + missing/weak test
- TODO/FIXME/HACK + confirmed runtime path
- broad `except Exception` / silent failure + user/operator impact
- fallback/default behaviour + security/privacy/evidence boundary
- docs/contract claim + current code path mismatch
- LR/drift warning + touched runtime surface
- recently changed code + missing regression test
- duplicated logic + inconsistent handling between sibling paths
- disabled/xfail/skipped test + active production path
- monkeypatch-heavy test surface + public function signature change
- provider/browser/native boundary + weak failure reporting
- accepted local fallback + production/staging assumption
- stale planned implementation claim + current code not matching it
- config/env/default value + runtime behaviour difference
- async/job/retry path + missing failure signal
- persistence/transaction boundary + partial success or silent rollback
- redaction/logging path + privacy or observability risk

Do not promote a spark to BUG unless B6 can answer:

- what contract is violated
- where it is violated
- what evidence shows the violation
- what user/system/security/operator impact could happen
- what nearby files are affected
- how a fix could regress something else
- what test would catch it

## Spark triage

Score each spark before creating a BUG candidate:

0 = ignore / noise
1 = weak lead; note only if repeated
2 = investigate with reads/searches
3 = form hypothesis if B6 answers are available
4 = create candidate + PoC attempt

Raise score when:

- runtime path is confirmed
- impact is user/security/privacy/operator visible
- existing tests miss it
- sibling code handles it differently
- LR/drift points to the same area
- recent changes touched it
- a repo contract names expected behaviour
- the failure mode is silent, partial, or hard to detect
- the same pattern appears in prior bug hunts

Lower score when:

- grep-only
- docs-only
- planned-work-only
- test-only with no runtime path
- behaviour is clearly intentional
- no contract can be named
- no meaningful impact can be explained
- evidence is stale or from old reports only

## Spark anti-drift rule

Spark discovery must make the auditor more precise, not more speculative.

The main auditor must not create BUG entries from:

- vague risks
- style preferences
- broad "could be better" claims
- grep hits without surrounding code reads
- TODO/FIXME comments without runtime impact
- docs/plans that are not verified against current code
- theoretical security issues with no reachable path
- missing tests alone, unless a real contract violation is demonstrated

If a spark cannot reach score 3, do not create a BUG candidate. Keep it as a note or ignore it.

## Sibling-pattern scan

When a spark looks real, search for sibling paths before creating the BUG candidate:

- same helper pattern in nearby files
- same exception handling pattern
- same persistence/fallback pattern
- same route/task/provider boundary
- same test fixture or monkeypatch surface
- same setting/env/config default
- same logging/redaction pattern

If siblings behave differently, record which sibling is the contract reference and why.
If siblings all behave the same and docs/tests support it, lower the spark score.

## B6b staging gate

B6b is only the PoC staging gate. It may reject or return weak or invalid PoCs before B7. It is not a Mode B threshold.

If the candidate advances to B7, the threshold must be one of:

- B7-lite
- B7-selective
- full B7

## Mode B PoC / counter-test lifecycle

Before B7:

- The main auditor creates or records the candidate PoC under `docs/bug_hunts/poc/BUG-YYYYMMDD-NNN/`.
- The PoC must be run or honestly reported as unable to run.
- A failing PoC is required before B7 unless the candidate is explicitly marked Needs more evidence.

During B7:

- Opposer 1 must attempt reproduction/disproof and may create/run a counter-test under the same candidate PoC folder.
- Opposer 2/3/4 may create/run focused counter-tests when needed for their assigned angle.
- Agent 5 may create/run an evidence test when full B7 or escalation requires it.
- Each agent must write its own test path, command, result, and interpretation into its own opposition section.

The main auditor must not create, run, or summarize a counter-test on behalf of an Opposer or Agent 5 after that reviewer is selected.

After opposition:

- The main auditor may synthesize the completed PoC/counter-test evidence table.
- If evidence is incomplete or a selected reviewer could not write/run its required evidence, mark the review incomplete or Needs more evidence.

## Threshold selection

### B7-lite

Use only for narrow low/medium candidates where reproduction is the main question and no security/privacy/fail-closed/cross-boundary risk exists.

Required reviewers:

- main auditor
- Opposer 1
- one relevant specialist reviewer

### B7-selective

Use when repo truth, architecture/security, or external semantics matter, but full B7 is not yet justified.

Required reviewers:

- main auditor
- Opposer 1
- selected Opposer 2/3/4 that match the candidate

### full B7

Mandatory for high-risk, P0/P1/P2, security/privacy/fail-closed, auth/session/CSRF/CORS/admin, billing/webhooks, storage/uploads/PDFs, assisted-submit/browser/CAPTCHA/2FA/final-submit, DB/migrations/runtime, provider/API semantics, cross-boundary bugs, contradictory evidence, or when selected opposers disagree.

Required reviewers:

- main auditor
- Opposer 1
- Opposer 2
- Opposer 3
- Opposer 4
- Agent 5

## Opposer 1 mandatory rule

Opposer 1 is mandatory for every B7 candidate because reproduction and disproof are the foundation of Mode B.

If Opposer 1 cannot clearly reproduce or disprove, do not cheaply validate.

## Escalation rules

If unsure, escalate.
If selected agents disagree, escalate.
If the candidate is P0/P1/P2, escalate to full B7.
If security/privacy/fail-closed/evidence-integrity is involved, escalate to full B7.
If cross-boundary runtime behaviour is involved, escalate to full B7.
If Opposer 1 cannot clearly reproduce or disprove, do not cheaply validate.
If a counter-test contradicts the PoC in a non-obvious way, escalate.
If the main auditor cannot decide after synthesis, escalate or mark Needs more evidence.

## Full B7 sequencing

When full B7 is selected, preserve the existing strict sequence from `SKILL.md`:

1. Spawn all four opposers first.
2. Wait for all four to complete.
3. Spawn Agent 5 with all four findings.
4. Main auditor must not read the opposition file between spawning the four opposers and Agent 5 completion.
5. Only after Agent 5 completes may the main auditor read all findings and write the final rebuttal.

Do not weaken no-peeking or sequential rules when full B7 is selected.

## Reviewer availability

Prefer the registered opposers and Agent 5. If one is unavailable, use the portable independent-review fallback in `SKILL.md`: spawn a separate subagent assigned that exact role, require it to own its artifact section and counter-test, and preserve the full B7 sequence. The main auditor must not perform or backfill that role. If no independent subagent can be spawned, report B7 as incomplete.

## Required Mode B reviewer spawn inputs

- BUG ID
- opposition file path
- assigned reviewer section
- candidate PoC folder path
- candidate summary
- original PoC path/command/result if present
- exact review angle
- allowed command boundary

## Artifact ownership

The Mode B opposition artifact is the source of truth for adversarial review.

- The main auditor owns the scaffold, candidate summary, evidence index, and final synthesis.
- The main auditor may create the opposition file, fill the header, write the bug candidate summary, reproduction context, and evidence table setup.
- Each selected Opposer owns only its own Opposer section and must write that section directly into the opposition file.
- Agent 5, when required, owns only the Agent 5 section and must write it directly into the opposition file.
- The main auditor must not fill Opposer 1/2/3/4 sections itself.
- Reviewer and Agent 5 sections must not be backfilled by the main auditor.
- General AI output is not a substitute for writing the required section into the review/opposition artifact.
- If a selected Opposer or Agent 5 cannot write its required section into the artifact, the review is incomplete and must be reported as incomplete instead of treating the reviewer as complete.
- For Mode B, the required selected Opposer sections in the Mode B opposition file must exist before Agent 5 or main auditor final synthesis can treat opposition as complete.

## Artifact write enforcement

Reviewer-owned sections must be authored directly by the assigned reviewer in the artifact.

The main auditor must not write, paste, transcribe, summarize, or backfill reviewer-owned sections or Agent 5 sections.

General AI output, terminal output, chat output, or copied reviewer text does not satisfy the artifact requirement.

If the selected reviewer cannot write directly to its required artifact section, the review is incomplete. The main auditor must report an orchestration/tooling gap instead of treating the reviewer as complete.

The main auditor may reference incomplete external reviewer output only as non-authoritative context, not as a completed reviewer section.

Final synthesis may begin only after all required reviewer-owned artifact sections exist.

For Mode B, Opposer 1/2/3/4 sections must be written directly into the Mode B opposition file by the assigned Opposer. The main auditor must not capture or paste Opposer output into these sections.

## Evidence synthesis before new tests

This section does not allow the main auditor to create, run, or summarize Opposer or Agent 5 counter-tests for them.

Before creating any new main-auditor test after opposition starts, synthesize the existing evidence first:

- original candidate entry
- original PoC test or curl command
- staging validator result
- all selected opposer findings
- all selected counter-tests
- Agent 5 audit and Agent 5 test if used
- current opposition file
- command outputs
- exact repo files
- relevant existing repo tests
- relevant official docs if semantics matter

Ask these questions:

1. Which existing test best proves the original claim?
2. Which existing test best disproves it?
3. Do any tests contradict each other?
4. Did any test fail to test the claimed contract?
5. Can an existing test be tightened instead of creating a new test?
6. What single unanswered question remains?

Only create a new test if the existing evidence does not answer the decisive question.

## Test evidence synthesis table

Before the final decision, populate the opposition file with:

```markdown
### Test evidence synthesis

| Evidence | Path/command | What it tested | Result | Supports bug | Disproves bug | Gaps |
|---|---|---|---|---|---|---|
| Main PoC | | | red/green/error/timeout | | | |
| Staging validator | | | | | | |
| Opposer 1 counter-test | | | | | | |
| Opposer 2 counter-test | not used / path | | | | | |
| Opposer 3 counter-test | not used / path | | | | | |
| Opposer 4 counter-test | not used / path | | | | | |
| Agent 5 test | not used / path | | | | | |
| Existing repo test | | | | | | |
```

The main auditor must decide from the table, not from vibes.

## Contradiction handling

If evidence conflicts:

- compare test intent against the claimed contract
- distinguish PoC failure from contract violation
- distinguish severity from existence
- distinguish a narrow bug from a broad claim
- escalate if the contradiction is non-obvious or unresolved

If the evidence cannot answer the decisive question, mark Needs more evidence instead of cheaply validating.

## Final decision anti-drift checklist

Before final decision, verify:

- [ ] The test evidence synthesis table is populated with real evidence
- [ ] At least one existing test was checked before creating any new test
- [ ] Escalation triggers were re-checked after opposition findings
- [ ] Downgrade-vs-reject logic was applied
- [ ] All selected opposer findings were read
- [ ] Agent 5 completed before the main auditor read any opposition findings when full B7 was selected
- [ ] No simulated or self-written opposing-agent reviews
- [ ] No timeouts, skips, or missing dependencies were treated as passes
- [ ] The decision is supported by synthesis, not by vibes
