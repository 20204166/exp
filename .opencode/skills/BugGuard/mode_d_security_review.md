# Mode D Main Auditor — Security Assurance and Hardening

This file is the lifecycle, threshold, and synthesis guide for BugGuard Mode D.

## Scope

Use this file when performing a Mode D security assurance and hardening review. Mode D is a security-first workflow that builds a threat model, verifies controls, identifies hardening opportunities, and proposes scoped hardening.

## Two phases

### D-audit

The main auditor performs the security analysis and writes the Security Review artifact's posture sections only. No app code. No normal repo test changes. Scoped PoC/counter-tests live under `docs/security_reviews/poc/SEC-YYYYMMDD-NNN/`.

### D-hardening

Only after (a) D-audit approves a concrete, scoped hardening proposal AND (b) the user explicitly approves implementation. D-hardening is a **Mode A run** scope-frozen to the accepted hardening proposal. Mode A owns the patch, regression tests, A4 patch-review oversight, and `lr secrets`/`lr impact`/`lr 7` gates. The resulting `PATCH-YYYYMMDD-NNN-review.md` links back to the SEC entry.

## Mandatory security research packs

Every Mode D run must consult all three security packs:

1. `security_foundations_pack.md` — reasoning model (assets, actors, trust boundaries, attack paths)
2. `security_testing_pack.md` — proof/disproof discipline (test types, safety, reproducibility)
3. `security_controls_pack.md` — control properties, failure modes, hardening considerations

For every Mode D run, the main auditor must record in the Security Review artifact:

```text
Foundations section used:
Why it was relevant:
What security question it informed:
What local repository evidence is still required:
```

Mandatory does not mean reading every section. Consult the relevant section from all three packs. Avoid irrelevant sections, performative research, and treating an external checklist as proof.

Mode D may also access `main_auditor_research_pack.md` and `research_link_pack.md` when the security question depends on language/framework/runtime semantics (Python, FastAPI, Starlette, SQLAlchemy, Celery, Redis, Playwright, Rust/native, provider SDK, testing/typing/lint/build).

Repo truth remains the final authority for repository behaviour.

## D-audit workflow

### D1. Scope and surface identification

Identify the target surface:

- exact files/routes/services/models/middleware/jobs/templates
- caller/callee chains
- runtime entry points
- public APIs/routes/tasks
- settings/env vars
- models/tables/migrations
- templates/static assets
- tests and fixtures
- monkeypatch surfaces
- feature flags
- deployment assumptions
- relevant docs/plans

Run `lr --list` and `lr impact` to choose relevant read-only LR checks. Use MCP `repo_search` / `repo_relevant_files` / `get_edit_context` for discovery.

### D2. Threat model construction

Build the posture model using `security_foundations_pack.md`:

- protected assets
- actors and attacker capabilities
- entry points
- data flows
- trust boundaries
- threat assumptions
- attacker-controlled input

Write these into the Security Review artifact's posture sections (not reviewer sections).

### D3. Existing controls map

Using `security_controls_pack.md`, inventory existing controls for the target surface:

- for each relevant control: classify as existing sufficient / existing partial / missing / compensating / deployment-dependent / configuration-dependent
- record the repo evidence path for each classification
- identify gaps between expected properties and existing controls

### D4. Suspected weaknesses

For each suspected weakness:

- state the attack preconditions
- map the attack path from entry point to impact
- record what repo evidence shows reachability
- identify what proof is still needed
- classify initial concern: vulnerability / hardening opportunity / accepted risk / existing sufficient control / needs more evidence

### D5. Security PoC

If a suspected weakness needs proof, create a security PoC under `docs/security_reviews/poc/SEC-YYYYMMDD-NNN/`. The PoC must:

- start from a confirmed entry point in repo code
- use realistic attacker preconditions
- assert the specific security property that fails
- record the exact code path from entry to impact
- be redacted (no weaponized payloads, no real secrets)

A PoC that fails to reproduce is evidence against the concern, not a test error.

### D6. Initial hardening proposal

If hardening is warranted, draft a scoped proposal:

- what control to add or strengthen
- what files to change
- what public contracts must be preserved
- what regression risks exist
- what tests would prove the hardening works

The proposal is **frozen** until D-audit concludes. D-hardening is Mode A, not D.

### D7. Adversarial review

Run the D7 threshold (see below). The main auditor does not write, paste, summarize, or backfill reviewer-owned sections.

## D7 threshold selection

### D7-lite

Use only for narrow single-control hardening questions with no security/privacy/fail-closed surface.

Required reviewers: main auditor + Opposer 1 + one relevant specialist reviewer.

### D7-selective

Use when repo truth, architecture/security, or external semantics matter but full D7 is not yet justified.

Required reviewers: main auditor + Opposer 1 + selected Opposer 2/3/4 that match the concern.

Agent 5 only if the threshold policy declares it.

### full D7

Mandatory for: security/privacy/fail-closed, auth/session/CSRF/CORS/admin, billing/webhooks, storage/uploads/PDFs, assisted-submit/browser/CAPTCHA/2FA/final-submit, DB/migrations/runtime, provider/API semantics, OAuth, email/provider integrations, SSRF/injection/path-traversal/deserialization, command-execution exposure, retries/idempotency/duplicate-execution, fail-open-vs-fail-closed, cross-boundary, contradictory evidence, or when selected opposers disagree.

Required reviewers: main auditor + Opposer 1 + Opposer 2 + Opposer 3 + Opposer 4 + Agent 5.

Because Mode D is security-first, most D runs land at full D7. The lite/selective tiers are real but narrow.

## Opposer 1 mandatory rule

Opposer 1 is mandatory for every D7 candidate because reproduction and disproof are the foundation of Mode D.

If Opposer 1 cannot clearly reproduce or disprove, do not cheaply validate.

## Escalation rules

- If unsure, escalate.
- If selected agents disagree, escalate.
- If security/privacy/fail-closed/evidence-integrity is involved, escalate to full D7.
- If cross-boundary runtime behaviour is involved, escalate to full D7.
- If Opposer 1 cannot clearly reproduce or disprove, do not cheaply validate.
- If a counter-test contradicts the PoC in a non-obvious way, escalate.
- If the main auditor cannot decide after synthesis, escalate or mark Needs more evidence.

## Full D7 sequencing

When full D7 is selected, preserve the strict sequence:

1. Spawn all four opposers first.
2. Wait for all four to complete.
3. Spawn Agent 5 with all four findings.
4. Main auditor must not read the Security Review's reviewer sections between spawning the four opposers and Agent 5 completion.
5. Only after Agent 5 completes may the main auditor read all findings and write the final rebuttal.

Do not weaken no-peeking or sequential rules when full D7 is selected.

## Reviewer availability

Prefer the registered opposers and Agent 5. If one is unavailable, use the portable independent-review fallback in `SKILL.md`: spawn a separate subagent assigned that exact role, require it to own its artifact section and counter-test, and preserve the full D7 sequence. The main auditor must not perform or backfill that role. If no independent subagent can be spawned, report D7 as incomplete.

## Evidence synthesis before new tests

Before creating any new main-auditor test after opposition starts, synthesize the existing evidence first:

- original posture model
- security PoC
- all selected opposer findings
- all selected counter-tests
- Agent 5 audit and test if used
- current Security Review artifact
- command outputs
- exact repo files
- relevant existing repo tests
- relevant official docs if semantics matter

Ask:
1. Which existing test best proves the original concern?
2. Which existing test best disproves it?
3. Do any tests contradict each other?
4. Did any test fail to test the claimed property?
5. Can an existing test be tightened instead of creating a new test?
6. What single unanswered question remains?

Only create a new test if existing evidence does not answer the decisive question.

## Contradiction handling

If evidence conflicts:

- compare test intent against the claimed security property
- distinguish PoC failure from property violation
- distinguish severity from existence
- distinguish a narrow gap from a broad claim
- escalate if the contradiction is non-obvious or unresolved

If evidence cannot answer the decisive question, mark Needs more evidence.

## Per-concern final decision

D-audit produces a decision per surfaced concern (not a single artifact-level verdict):

- **Existing sufficient control** — control exists and is proven adequate; nothing to do.
- **Hardening opportunity** — not a vulnerability, but an improvement is available; queued for D-hardening if user approves.
- **Vulnerability** — proven contract-violation requiring a patch; must transition to Mode B.
- **Accepted risk** — residual; documented with compensating controls and re-review date.
- **Needs more evidence** — inconclusive; SEC entry marked for re-audit.

## Transitions

Mode D enters the existing transition protocol. New and updated transitions:

- **D-audit → B**: D-audit confirms a reproducible contract-violation vulnerability. Candidate moves to Mode B for full B7 + Agent 5 + ledger capture. SEC entry links the BUG entry.
- **D-audit → A (D-hardening)**: D-audit approves a scoped hardening proposal AND user approves implementation. D-hardening IS a Mode A run. A links PATCH-YYYYMMDD-NNN-review.md from the SEC entry.
- **D-audit → Accepted risk**: posture acceptable with compensating controls; recorded in SEC + index.
- **D-audit → Needs more evidence**: inconclusive; SEC entry marked for re-audit.
- **B → D**: Opposer 3 during full B7 finds systemic posture issues. Candidate stays in B; separate D run opened.
- **A → D**: A uncovers deep security questions. A stabilizes; then D opens.
- **C → D**: only when C surfaces a security blocker; C pauses; D owns posture.

All transitions use the explicit transition block (From/To/Trigger/Reason/Scope impact/Artifacts carried forward/Validation reset needed/User approval needed).

D never transitions to A or C directly for code-writing. D-hardening IS a Mode A run, not a D-to-A transition.

## Final decision anti-drift checklist

Before final decision, verify:

- [ ] All three security packs were consulted and usage recorded
- [ ] The test evidence synthesis table is populated with real evidence
- [ ] At least one existing test was checked before creating any new test
- [ ] Escalation triggers were re-checked after opposition findings
- [ ] Per-concern classification was applied honestly
- [ ] All selected opposer findings were read
- [ ] Agent 5 completed before the main auditor read any opposition findings when full D7 was selected
- [ ] No simulated or self-written opposing-agent reviews
- [ ] No timeouts, skips, or missing dependencies were treated as passes
- [ ] The decision is supported by synthesis, not by vibes
- [ ] No app code or normal repo tests were changed during D-audit
- [ ] Vulnerability concerns are routed to Mode B, not self-validated in D

## Final report fields

```text
BugGuard mode: Mode D - security assurance and hardening (D-audit)
Mode D review ID: SEC-YYYYMMDD-NNN
Target and scope:
Posture model: (assets / actors / entry points / trust boundaries / data flows)
D7 threshold: D7-lite / D7-selective / full D7
Security review file: docs/security_reviews/SEC-YYYYMMDD-NNN-review.md
Risk level: low / medium / high / contradictory
Per-concern decisions: (sufficient control / hardening / vulnerability / accepted risk / needs more evidence)
Vulnerabilities transitioned to Mode B: (BUG IDs, if any)
Hardening proposals queued for D-hardening: (surface + scope, if any)
Accepted risks recorded: (concern + compensating controls + re-review date)
Research packs used: (sections used from each of the 3 packs + main/research_link pack)
Adversarial review: (selected opposers + Agent 5 result and verdict)
LR checks run (read-only):
Commands run / not run and why:
Remaining risk:
Next safest action: (D-hardening → Mode A patch / re-audit / accept-and-close)
```
