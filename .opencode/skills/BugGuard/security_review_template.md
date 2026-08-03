# Security Review — SEC-YYYYMMDD-NNN

**Target surface:**
**Created:** YYYY-MM-DD HH:MM
**D7 threshold:** D7-lite / D7-selective / full D7
**Mode D review file:** `docs/security_reviews/SEC-YYYYMMDD-NNN-review.md`

## Posture model (main auditor writes only this)

### Target and scope

### Protected assets

### Actors and attacker capabilities

### Entry points

### Data flows

### Trust boundaries

### Threat assumptions

### Existing controls map

| Control | Status | Repo evidence | Gap |
|---|---|---|---|
| | | | |

(Status: existing sufficient / existing partial / missing / compensating / deployment-dependent / configuration-dependent)

### Suspected weaknesses

| # | Weakness | Preconditions | Attack path | Evidence lead | Initial classification |
|---|---|---|---|---|---|

### Evidence index

| Evidence | Path | What it tests | Result |
|---|---|---|---|

### Initial risk assessment

| # | Concern | Initial severity | Initial classification |
|---|---|---|---|

### Proposed security tests

| Reviewer | Test purpose | What to run |
|---|---|---|

### Initial hardening proposal (frozen until D-audit conclusion)

### Mode D research-pack usage

```text
Foundations section used:
Why it was relevant:
What security question it informed:
What local repository evidence is still required:

Testing section used:
Why it was relevant:
What security question it informed:
What local repository evidence is still required:

Controls section used:
Why it was relevant:
What security question it informed:
What local repository evidence is still required:
```

---

## Reviewer-owned sections

### Opposing Agent 1 — Reproduction Skeptic

**Goal:** Prove the suspected weakness is not reproducible, the PoC is invalid, or impact is overstated.

**Reproduction attempts:**

**Challenge:**

**Repo evidence checked:**

**Commands run:**

**Counter-test results:**
- Saved at: `docs/security_reviews/poc/SEC-YYYYMMDD-NNN/opposer1_*.py`
- First run:
- Iteration:
- Second run:
- Test proves/disproves:

**Verdict:** Disproven / Weak / Still plausible / Strong

### Opposing Agent 2 — Repo-Truth Skeptic

**Goal:** Prove repo contracts already handle the concern, or another layer covers it.

**Challenge:**

**Repo evidence checked:**

**Commands run:**

**Counter-test results:**
- Saved at: `docs/security_reviews/poc/SEC-YYYYMMDD-NNN/opposer2_*.py`
- First run:
- Iteration:
- Second run:
- Test proves/disproves:

**Verdict:** Disproven / Weak / Still plausible / Strong

### Opposing Agent 3 — Architecture/Security Skeptic

**Goal:** Prove impact or severity is overstated, no trust boundary is crossed, or fail-closed behaviour holds.

**Security boundary analysis:**

**Data flow trace:**

**Threat model assessment:**

**Challenge:**

**Repo evidence checked:**

**Commands run:**

**Counter-test results:**
- Saved at: `docs/security_reviews/poc/SEC-YYYYMMDD-NNN/opposer3_*.py`
- First run:
- Iteration:
- Second run:
- Test proves/disproves:

**Verdict:** Disproven / Weak / Still plausible / Strong

### Opposing Agent 4 — External-Research Skeptic

**Goal:** Prove official standards/framework/library/security docs contradict the claim or do not apply to the repo.

**Research question:**

```text
Research question:
Repo evidence that triggered it:
Pack used: security_controls_pack.md / security_testing_pack.md / security_foundations_pack.md / research_link_pack.md
Why this pack is enough:
How the answer could change the decision:
```

**External docs used:**

**Repo-specific implication:**

**Local evidence still needed:**

**Counter-test results:**
- Saved at: `docs/security_reviews/poc/SEC-YYYYMMDD-NNN/opposer4_*.py`
- First run:
- Iteration:
- Second run:
- Test proves/disproves:

**Verdict:** Disproven / Weak / Still plausible / Strong

---

## Agent 5 — Superpower Evidence Auditor

**Agent 5 required by this threshold:** yes / no
**Agent 5 run for this review:** yes / no
**Reason:**

### Inputs read
- Security Review posture sections:
- PoC:
- Opposer 1 section:
- Opposer 2 section:
- Opposer 3 section:
- Opposer 4 section:
- exact repo files:
- LR/drift evidence:
- security research packs:

### Additional repo probes

| Probe | Result | Why it matters |
|---|---|---|

### Additional LR/drift evidence

| Command | Result | Interpretation |
|---|---|---|

### Prior security review pattern match
- Similar prior SEC:
- Similar prior BUG:
- Reusable lesson:

### Sibling-surface search
- nearby files checked:
- same pattern elsewhere:
- result:

### Phase 3 — Own evidence test

**Saved at:** `docs/security_reviews/poc/SEC-YYYYMMDD-NNN/agent5_*.py`

**Initial test design:**
- Logic:
- Test cases:

**First run:**
- Result:
- Key findings:
- Timing:

### Phase 4 — Test iteration

**Changes made:**

**Second run:**
- Result:
- Key findings:
- Timing:

**Empirical verdict from test results:**

### Agent 5 conclusion

**Decision pressure:** strengthens / weakens / changes severity / needs more evidence
**Reason:**
**What main auditor must verify next:**

---

## Main auditor rebuttal and synthesis

**Response to Opposer 1:**

**Response to Opposer 2:**

**Response to Opposer 3:**

**Response to Opposer 4:**

**Response to Agent 5:**

**Additional repo evidence gathered:**

**Additional research gathered:**

## Test evidence synthesis

| Evidence | Path/command | What it tested | Result | Supports concern | Disproves concern | Gaps |
|---|---|---|---|---|---|---|
| Main PoC | | | | | | |
| Opposer 1 | | | | | | |
| Opposer 2 | | | | | | |
| Opposer 3 | | | | | | |
| Opposer 4 | | | | | | |
| Agent 5 | | | | | | |
| Existing repo test | | | | | | |

## Per-concern final decision table

| # | Concern | Classification | Severity | Evidence | Transition |
|---|---|---|---|---|---|

(Classification: existing sufficient control / hardening opportunity / vulnerability / accepted risk / needs more evidence)

## Agent contradiction sweep

| Agent | Main claim | Evidence type | Strength | What it disproves | What it does NOT disprove |
|---|---|---|---|---|---|
| Opposer 1 | | | | | |
| Opposer 2 | | | | | |
| Opposer 3 | | | | | |
| Opposer 4 | | | | | |
| Agent 5 | | | | | |

## Main auditor final synthesis

**Were all three security packs consulted?**

**Were all selected opposer findings read?**

**Was Agent 5 required? Was it run?**

**Did any opposition finding change the classification?**

**Final per-concern decisions:**

## Transitions

| Concern | From | To | Trigger | Artifacts carried forward |
|---|---|---|---|---|

## Security review entry in index

Update `docs/security_reviews/index.md` with the SEC entry and final status.
