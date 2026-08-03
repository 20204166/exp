# Opposition Review — BUG-YYYYMMDD-NNN

**Candidate bug:** BUG-YYYYMMDD-NNN
**Created:** YYYY-MM-DD HH:MM
**Current cycle:** 1 / 3
**Candidate entry source:** `docs/bug_hunts/bugs_found/bugs_found.md#bug-yyyymmdd-nnn-short-title`

## Artifact ownership

The Mode B opposition artifact is the source of truth for adversarial review.

- The main auditor owns the scaffold, candidate summary, evidence index, and final synthesis.
- Each selected Opposer owns only its own Opposer section and must write that section directly into the artifact.
- Agent 5, when required, owns only the Agent 5 section and must write it directly into the artifact.
- The main auditor must not fill reviewer-owned sections.
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

## PoC and counter-test ownership

Candidate PoC path:

```text
docs/bug_hunts/poc/BUG-YYYYMMDD-NNN/
```

Each selected reviewer must record its own evidence here:

```text
Reviewer:
Artifact path:
Command run:
Result:
Interpretation:
Supports bug:
Disproves bug:
Gaps:
```

The main auditor must not backfill reviewer test results.

## Original candidate summary

## Cycle 1

### Opposing Agent 1 — Reproduction Skeptic

**Full report required.** Must write a detailed report covering every reproduction attempt, what was observed, and whether the PoC passed or failed. If insufficient evidence to disprove, expand scope via alternative paths, different environments, input variations, edge cases.

**Goal:** Prove this is not reproducible.

**Different angle required:** reproduction path, command validity, local-environment dependency, weak proof.

**Reproduction attempts:** (detailed log of every attempt including command, env, input, observed output)

**Each attempt:**
- **Attempt 1:** command/env/input → observed output → pass/fail relative to PoC
- **Attempt 2:** ...
- ...

**Scope expansion:** (if evidence insufficient, what alternative approaches were tried?)

**Challenge:**

**Repo evidence checked:**

**Commands run:**

**External research used:**

**Counter-test results:**
- Saved at: `docs/bug_hunts/poc/BUG-YYYYMMDD-NNN/agent1_counter_test.py`
- First run: (pass/fail/error/timeout, output summary, timing)
- Iteration: (what was fixed/changed, or "No changes needed")
- Second run: (pass/fail/error/timeout, output summary, timing)
- Test proves/disproves: (what the empirical results show)

**Verdict:** Disproven / Weak / Still plausible / Strong

### Opposing Agent 2 — Repo-Truth Skeptic

**Goal:** Prove repo contracts already allow this behaviour.

**Different angle required:** docs/tests/contracts/feature flags/fallbacks/runtime path.

**Challenge:**

**Repo evidence checked:**

**Commands run:**

**External research used:**

**Counter-test results:**
- Saved at: `docs/bug_hunts/poc/BUG-YYYYMMDD-NNN/agent2_counter_test.py`
- First run: (pass/fail/error/timeout, output summary, timing)
- Iteration: (what was fixed/changed, or "No changes needed")
- Second run: (pass/fail/error/timeout, output summary, timing)
- Test proves/disproves: (what the empirical results show)

**Verdict:** Disproven / Weak / Still plausible / Strong

### Opposing Agent 3 — Architecture/Security Skeptic

**Full report required.** Must write a detailed report covering every security boundary, data flow, and threat model analysis performed. If insufficient evidence to disprove, expand scope — trace deeper into call chains, check adjacent services, review logging/audit trails, examine error-handling paths, test alternative input vectors.

**Goal:** Prove impact or severity is overstated.

**Different angle required:** reachability, boundary analysis, threat model, severity downgrade, fix regression risk.

**Security boundary analysis:** (which boundaries exist, how does the bug cross or not cross them?)

**Data flow trace:** (trace the data from input to storage/output, noting protections at each step)

**Threat model assessment:** (what threat scenarios were considered, which are ruled out, which need more evidence)

**Scope expansion:** (if evidence insufficient, what deeper traces or adjacent paths were checked?)

**Challenge:**

**Repo evidence checked:**

**Commands run:**

**External research used:**

**Counter-test results:**
- Saved at: `docs/bug_hunts/poc/BUG-YYYYMMDD-NNN/agent3_counter_test.py`
- First run: (pass/fail/error/timeout, output summary, timing)
- Iteration: (what was fixed/changed, or "No changes needed")
- Second run: (pass/fail/error/timeout, output summary, timing)
- Test proves/disproves: (what the empirical results show)

**Verdict:** Disproven / Weak / Still plausible / Strong

### Opposing Agent 4 — External-Research Skeptic

**Goal:** Prove the claim misunderstands framework/library/security behaviour.

**Different angle required:** official docs, standards, library semantics, documented edge cases.

**Challenge:**

**Repo evidence checked:**

**Commands run:**

**External research used:**

**Counter-test results:**
- Saved at: `docs/bug_hunts/poc/BUG-YYYYMMDD-NNN/agent4_counter_test.py`
- First run: (pass/fail/error/timeout, output summary, timing)
- Iteration: (what was fixed/changed, or "No changes needed")
- Second run: (pass/fail/error/timeout, output summary, timing)
- Test proves/disproves: (what the empirical results show)

**Verdict:** Disproven / Weak / Still plausible / Strong

## Agent 5 — Superpower Evidence Auditor

### Inputs read
- candidate entry:
- opposition file:
- prior bug hunts:
- rejected hypotheses:
- repo docs:
- exact files:
- LR commands/list:

### Additional repo probes
| Probe | Result | Why it matters |
|---|---|---|

### Additional LR/drift evidence
| Command | Result | Interpretation |
|---|---|---|

### Prior bug-hunt pattern match
- Similar prior bug:
- Similar rejected hypothesis:
- Reusable lesson:

### External research pack used
| Source | Type | What it proves / disproves | Primary or secondary |
|---|---|---|---|

### Validated search set performed
- official language docs:
- official framework/library docs:
- official tool docs:
- changelog/release notes:
- issue tracker search:
- Stack Overflow search:
- sibling-bug repo search:
- prior bug-hunt search:

### New sibling-bug search
- nearby files checked:
- same pattern elsewhere:
- cross-language variant checked:
- prior bug-hunt/rejected-hypothesis match:
- result:

### Phase 3 — Own counter-test

**Saved at:** `docs/bug_hunts/poc/BUG-YYYYMMDD-NNN/agent5_counter_test.py`

**Initial test design:**
- Logic: (what does the test assert?)
- Test cases: (N tests)

**First run:**
- Result: (X/N passed, Y failed, Z timeout/error)
- Key findings: (what did the first run reveal?)
- Timing: (total runtime)

### Phase 4 — Test iteration

**Changes made based on re-read:**
- (what was refined/added/removed and why)

**Second run:**
- Result: (X/N passed, Y failed, Z timeout/error)
- Key findings: (what did the second run prove/disprove?)
- Timing: (total runtime)

**Empirical verdict from test results:**
- (what the two test runs conclusively show)

### Agent 5 conclusion
**Decision pressure:** strengthens validation / weakens validation / changes severity / needs more evidence

**Reason:** (must incorporate test results as primary evidence)

**What main auditor must verify next:**

## Main auditor rebuttal

**Response to Agent 1:**

**Response to Agent 2:**

**Response to Agent 3:**

**Response to Agent 4:**

**Response to Agent 5:**

**Additional repo evidence gathered:**

**Additional online research gathered:**

**Final decision:** Validated bug / Not a bug / Needs more evidence

**Action taken in `bugs_found/bugs_found.md`:**

**Opposition file cleanup:** Delete / Archive by repo policy

---

## Bug report format

Each candidate or validated bug entry in `bugs_found/bugs_found.md` must use:

```markdown
## BUG-YYYYMMDD-NNN — Short title

**Ledger status:**
- [ ] Candidate
- [ ] Under opposition
- [ ] Needs more evidence
- [ ] Not a bug
- [ ] Validated bug
- [ ] Validated downgraded bug
- [ ] Accepted risk
- [ ] Fixed

**Status:** Candidate / Under opposition / Validated bug / Validated downgraded bug / Not a bug / Accepted risk / Needs more evidence / Fixed
**Severity:** P0 / P1 / P2 / P3
**Confidence:** High / Medium / Low
**Initial severity:** P0 / P1 / P2 / P3
**Final severity:** P0 / P1 / P2 / P3
**Downgrade rationale:** Only required when final severity is lower than initial severity.
**Final decision type:** Validated bug / Validated downgraded bug / Not a bug / Accepted risk / Needs more evidence
**Area:** api / services / jobs / ui / models / infra / tooling / docs / native / tests
**Primary file(s):**
**Related file(s):**
**Detected by:**
**Commands/evidence:**
**Opposition file:** `docs/bug_hunts/opposition/BUG-YYYYMMDD-NNN-opposition.md` while under review; deleted after final decision unless archived by repo policy.

### Summary

**Spark source:** code pattern / test gap / docs mismatch / LR drift / sibling inconsistency / runtime failure / other

### Expected behaviour / contract

### Actual behaviour

### Why this is a bug

### User/security/operational impact

### Repo evidence

### External research evidence

### Reproduction or static proof

### Nearby code and affected surfaces

### Proposed safe fix direction

### Regression risks of the fix

### Tests/checks to add or run

### Five-agent adversarial review with PoC disproval

#### Opposing Agent 1 — Reproduction Skeptic
- Full report link: (path to opposition file section)
- Reproduction attempts: (count, outcome summary)
- Challenge:
- Evidence used:
- Scope expansion performed: (yes/no — what was tried)
- Verdict:

#### Opposing Agent 2 — Repo-Truth Skeptic
- Challenge:
- Evidence used:
- Verdict:

#### Opposing Agent 3 — Architecture/Security Skeptic
- Full report link: (path to opposition file section)
- Security boundary analysis: (summary)
- Data flow trace: (summary)
- Challenge:
- Evidence used:
- Scope expansion performed: (yes/no — what was tried)
- Verdict:

#### Opposing Agent 4 — External-Research Skeptic
- Challenge:
- Evidence used:
- Verdict:

#### Agent 5 — Superpower Evidence Auditor
- Additional probes:
- LR/drift evidence:
- Prior bug-hunt pattern match:
- External research pack used:
- Sibling-bug search:
- Decision pressure:
- Verdict:

### Agent contradiction sweep

| Agent | Main claim | Evidence type | Strength | What it disproves | What it does NOT disprove |
|---|---|---|---|---|---|
| Agent 1 | | | | | |
| Agent 2 | | | | | |
| Agent 3 | | | | | |
| Agent 4 | | | | | |
| Agent 5 | | | | | |

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

### Main auditor final decision table

| Question | Answer | Evidence |
|---|---|---|
| Original claim fully proven? | yes/no/partial | |
| Original severity still valid? | yes/no | |
| Any narrower bug remains? | yes/no | |
| Affected scope after review | production/staging/local/dev/CI/docs/config/tooling | |
| PoC still valid after narrowing? | yes/no/not run | |
| Counter-tests disprove whole claim? | yes/no/partial | |
| Agent 5 found sibling pattern? | yes/no | |
| Final status | Validated bug / Validated downgraded bug / Not a bug / Needs more evidence / Accepted risk | |
| Final severity | P0/P1/P2/P3 | |

### Main auditor rebuttal

### Final validation decision
```
