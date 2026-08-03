---
name: BugGuard
description: Use this skill as a no-regression bug-prevention, bug-hunt, safe performance-improvement, and security assurance workflow for code edits and standalone audits. It validates changes with repo truth, LR, drift checks, targeted tests, focused research, four opposition reviewers, and Agent 5 Superpower Evidence Audit before documenting confirmed or disproven bug entries.
---

# BugGuard

## Purpose

Use this skill to prevent bugs from entering the repo and to find existing bugs without making unsafe changes.

This skill has four modes:

1. Code-edit validation mode - use before, during, and after writing or changing code.
2. Standalone bug-hunt mode - use for a no-code-change audit that writes confirmed bugs to Markdown reports.
3. Safe performance improvement mode - use for scoped performance work where behaviour must remain identical.
4. Security assurance and hardening mode - use for security posture review, threat modelling, control verification, and scoped hardening of security-sensitive surfaces.

The skill is strict: it does not treat suspicions as bugs, does not treat timeouts as passes, and does not allow broad rewrites or weak validation. A bug is only confirmed when repo evidence, expected behaviour, actual behaviour, impact, and adversarial review all support it.

## Persistent audit files

Use versioned bug ledger volumes under `bugs_found/` (active file named by `docs/bug_hunts/index.md`), one temporary opposition file per candidate bug (`opposition/BUG-YYYYMMDD-NNN-opposition.md`), and versioned rejected-hypotheses volumes under `rejected/`. `index.md` is the master navigation hub and has no line limit.

The active `bugs_found_N.md` contains only BUG entries - status, severity, confidence, timestamps, fix status, links, final decision - no raw opposition debates. The active `rejected_hypotheses_N.md` holds longer rejected investigations worth remembering.

All four reviewers write into the same opposition file per candidate. Agent 5 reads those sections and writes its audit into the same file. The main auditor reads all sections, validates, then updates the active `bugs_found_N.md`. After the final decision, delete the opposition file unless repo policy requires archiving.

## Support files

Read these files when the relevant workflow is active:

- `patch_review_template.md` - template for Mode A `PATCH-YYYYMMDD-NNN-review.md` files.
- `mode_a_patch_review.md` - detailed Mode A patch-review lifecycle, validator rules, Agent 5 checklist, and no-peeking sequence.
- `validation_commands.md` - direct static checks and long-running validation log patterns.
- `opposition_template.md` - Mode B BUG/opposition report format.
- `research_link_pack.md` - official-doc research links and bespoke command sets.
- `mode_c_performance.md` - Mode C correctness-first performance workflow, cache/query/async/browser safety checks, focused/deeper research-pack use, and before/after evidence format.
- `mode_c_opposition_template.md` - Mode C adversarial review template for performance patch safety, measurement honesty, contract preservation, and Agent 5 evidence audit.
- `mode_b_main_auditor.md` - Mode B threshold selection, evidence synthesis, and escalation rules.
- `main_auditor_research_pack.md` - focused official-doc research guide for the main auditor in Mode A and Mode B.
- `mode_d_security_review.md` - Mode D D-audit lifecycle, D7 threshold selection, evidence synthesis, and escalation rules.
- `security_review_template.md` - Mode D Security Review artifact format with posture sections and reviewer-owned sections.
- `security_foundations_pack.md` - Mode D mandatory pack: reasoning model for security analysis (assets, actors, trust boundaries, attack paths).
- `security_testing_pack.md` - Mode D mandatory pack: proof/disproof discipline (seven test types, safety, reproducibility).
- `security_controls_pack.md` - Mode D mandatory pack: control properties, failure modes, and hardening considerations.

## Trigger conditions

Use this skill whenever an agent is about to write/edit/refactor/delete/move code; change public routes/schemas/payloads/settings/storage/jobs/providers/templates/tooling; investigate suspected bugs; run a repo-wide audit; review changes before merge; or produce a bug report.

Always trigger for high-risk surfaces: auth/sessions/CSRF/CORS/admin, billing/Stripe/webhooks, storage/uploads/PDFs, delay providers/evidence, assisted-submit/browser/CAPTCHA/2FA, Celery/Redis, DB models/migrations, runtime settings/env, privacy/redaction/logging, LR/drift/MCP/dependency tooling, public API contracts/UI routes/templates, native/frontend/build.

Use Mode C when the user asks to improve performance, speed up a path, reduce repeated work, reduce query count, reduce memory use, or optimize validation/build/runtime time.

Use Mode D when the user asks for a security review, threat model, control verification, hardening assessment, or posture audit of a security-sensitive surface. Mode D is security-first: it builds a threat model, verifies controls, identifies hardening opportunities, and proposes scoped hardening. D-audit changes no app code; D-hardening delegates the patch to Mode A.

## Non-negotiable rules

Never:

- change code during standalone bug-hunt mode
- change tests during standalone bug-hunt mode
- change requirements, env files, migrations, baselines, generated files, or snapshots unless the user explicitly asked for an implementation task
- run writer/apply commands during audit mode
- run destructive commands
- run live production service calls
- call live Stripe, R2/S3, Sentry, OAuth, email, provider, browser-submit, or payment endpoints unless explicitly required and safe
- print secrets, env values, API keys, tokens, cookies, OAuth material, raw provider payloads, raw OCR text, email bodies, user uploads, DB rows, private URLs, or full raw logs
- mark a risk as a bug without proof
- treat a timeout, skipped command, missing dependency, or local environment failure as a pass
- propose a broad rewrite when a scoped fix is possible
- weaken security, privacy, fail-closed, redaction, auth, CSRF, session, final-submit, or evidence-integrity boundaries
- change LR check numbering, LR semantics, explicit-only policy, or drift baseline meaning without a separate approved tooling task
- claim whole-repo validation unless the relevant whole-repo checks actually ran and passed
- spawn `bugguard-agent5` during normal agent work or from persona/context alone
- create `.opencode/agents/bugguard-opposer-*.md` during an active BugGuard run
- simulate or self-write opposing-agent reviews when real subagents are required
- treat unavailable registered BugGuard agents as permission for the main auditor to perform an opposer or Agent 5 role
- hardcode, assume, or invent model IDs for BugGuard agents
- use a model mismatch as a reason to simulate or skip an opposing agent

## Portable independent-review fallback

Prefer the registered `bugguard-opposer-1` through `bugguard-opposer-4` and `bugguard-agent5` agents. If any required registered agent is unavailable, the main auditor may spawn a separate independent subagent for that exact role instead. This fallback does not create or register agent files during a run.

Each fallback reviewer must receive the role-specific prompt, evidence scope, artifact path and owned section, counter-test responsibility, and sequencing constraints of the unavailable role. It must run in a separate subagent session from the main auditor and write its own section directly into the required artifact. A single generic review cannot replace multiple required roles.

The main auditor must never act as an opposer or Agent 5, write or backfill their sections, or present its own analysis as independent review. If the environment cannot spawn independent subagents that can complete their required artifact sections, the required adversarial validation is incomplete and must be reported as incomplete.

## Core principle

Every edit and every bug claim must survive this question:

```text
What evidence proves this is safe or proves this is a real bug?
```

Evidence may include exact code paths, exact tests, route/task/model/settings registration, repo docs that define a contract, LR/drift/static/test output, official framework/library/security documentation, reproduction steps, adversarial review notes, and Agent 5 evidence.

Grep hits are leads, not proof. Docs/plans are not implementation proof unless the claim is explicitly about documentation or planned work.

## RailRefund MCP

When a `railrefund` MCP server is connected, prefer its tools over ad-hoc grep/shell for discovery and read-only LR planning. MCP search hits are still leads, not proof - read exact files before claiming a bug or signing off an edit.

Prefer:

- `repo_search` for symbols, routes, settings, tests, and contracts
- `repo_relevant_files` / `get_edit_context` for scoped edit/audit context
- `docs_lookup` / `guidelines_lookup` for hard rules and contracts
- `get_plan_context` / `get_drift_context` for planned work and drift surfaces
- `lr_checks` / `lr_version` / `lr_version_report` / `recommend_lr_checks` for LR planning
- `lr_run_readonly` for allowlisted read-only LR

`lr_run_readonly` is read-only and auto-backgrounds every check (`lr <check> -b`): the call returns instantly with PID/log-path/`--view`/`-b stop` info, so read results with `lr <check> --view` in a shell. It never substitutes for running real `lr` gates through the CLI before commit or push.

## Completion requirement

Once this skill has been invoked for a task, it must be completed in full. Do not stop mid-cycle and declare a result without reaching a real final decision.

- For full A4 or full B7 validation, do not skip a required skeptic pass. All required opposing agents plus Agent 5 run, with no merged summary standing in for one.
- A reviewer only counts when its findings are durably captured in the candidate's opposition file or the repo's explicit equivalent.
- Do not treat a timeout, skipped command, missing dependency, or partial read as sufficient to finish a step.
- Do not exit standalone bug-hunt mode partway through the folder-by-folder audit without stating which folders were not reached and why.
- Do not mark a bug `Validated bug` or `Not a bug` without the main auditor rebuttal step actually reading all required validator findings and Agent 5 when used.

## Mode Selector / Transition Protocol

Use the mode selector before starting BugGuard work and whenever evidence changes.

Mode selection:

- Use **Mode A** for scoped code edits, correctness fixes, normal implementation, or repairing a bug introduced by the current patch.
- Use **Mode B** for standalone no-code bug hunts, suspected pre-existing bugs, broad audits, or candidates that need PoC/opposition before implementation.
- Use **Mode C** for scoped performance improvements where behaviour must remain identical.
- Use **Mode D** for security assurance and hardening of a named surface: threat modelling, control verification, hardening proposals, and accepted-risk documentation. D-audit is read-only; D-hardening delegates the patch to Mode A.

If a task overlaps modes, choose the stricter path:

- correctness risk beats performance goal
- security/privacy/fail-closed risk beats speed
- suspected pre-existing bug beats opportunistic patching
- unclear evidence escalates instead of guessing

Mode transitions must be explicit:

```text
Mode transition:
From:
To:
Trigger evidence:
Reason:
Scope impact:
Artifacts carried forward:
Validation reset needed:
User approval needed: yes/no
```

A transition is not a validation result. The new mode must still complete its own required gates.

Safe transition rules:

- **A → C:** allowed when the task is primarily performance-related and behaviour must remain identical.
- **C → A:** required when the optimization introduces or exposes a correctness bug that must be fixed in the current patch.
- **C → B:** required when performance work discovers a suspected pre-existing bug outside the optimization scope. Pause code changes and treat it as a bug-hunt candidate unless the user explicitly approves implementation.
- **B → A:** allowed only after a bug is validated and the user approves implementation.
- **B → C:** allowed only when the validated issue is specifically a performance improvement with identical behaviour and the user approves implementation.
- **A → B:** use when a scoped code edit uncovers an unrelated suspected pre-existing bug. Do not silently fix it inside the current patch.
- **D-audit → B:** D-audit confirms a reproducible contract-violation vulnerability. Candidate moves to Mode B for full B7 + Agent 5 + ledger capture. SEC entry links the BUG entry.
- **D-audit → A (D-hardening):** D-audit approves a scoped hardening proposal AND user approves implementation. D-hardening IS a Mode A run scope-frozen to the proposal. A links PATCH-YYYYMMDD-NNN-review.md from the SEC entry.
- **B → D:** Opposer 3 during full B7 finds systemic posture issues beyond the candidate. Candidate stays in B; separate D run opened.
- **A → D:** A uncovers deep security questions (e.g. BOLA risk after edits). A stabilizes; then D opens for the surface.
- **C → D:** only when C surfaces a security blocker. C pauses; D owns posture.

D never transitions to A or C directly for code-writing. D-hardening IS a Mode A run, not a D-to-A transition. D does not optimize. D does not write repo regression tests (those are Mode A in D-hardening).

Patch-introduced bugs stay in **Mode A** until repaired.
Performance regressions stay in **Mode C** unless they reveal correctness breakage.
Standalone bug-hunt mode never changes app code or tests.

Final reports must include the mode path, for example:

```text
Mode path: A → C → A
Transition reasons:
Current final mode:
```

## Mode A - Code-edit validation workflow

Use this mode when writing or changing code. Mode A is for implementing and validating scoped code changes. It is not the full standalone bug-hunt proof workflow.

### Mode A declaration

Every Mode A run starts with:

```text
BugGuard mode: Mode A - code-edit validation
Risk level: low / medium / high / contradictory
Validator threshold: none / selective / full A4
Patch-review file: not needed / created at <path>
Reason: <one compact sentence>
```

### A1 before editing

Build a scoped edit context. Use `git status --short`, `./lr --list`, and `./lr impact`. If `lr` is unavailable, use equivalent read-only commands. Identify target files, direct callers/callees, runtime entry points, public APIs/routes/tasks/classes, settings/env vars, models/tables/migrations, templates/static assets, tests and fixtures, monkeypatch surfaces, hidden-test-sensitive surfaces, security/privacy/runtime boundaries, relevant docs/plans, recommended LR checks, and drift surfaces.

### A1a regression evidence

Mode A creates or updates repository tests. It does not create or overwrite bug-hunt PoC folders.

- If the change needs proof, add a focused regression test or minimal repro in the repo test tree.
- If the fix came from an existing bug-hunt candidate, preserve that candidate's PoC and add a regression test that proves the fix.
- Do not overwrite an unrelated PoC, counter-test, or audit artifact from another candidate.

### A2 during editing

Keep the patch narrow. Make the smallest change justified by repo evidence. Do not do unrelated cleanup, broad formatting, dependency upgrades, public API changes, schema changes, or behaviour changes unless the user explicitly asked.

Preserve public names, signatures, routes, payload shapes, status codes, logs/redaction semantics, monkeypatch surfaces, hidden-test expectations, fail-open/fail-closed behaviour, feature flags, explicit-only gates, and fallback behaviour.

### A3 after editing

Run the smallest meaningful validation set for the changed surface. Start with `git diff --stat`, `git diff --check`, `./lr impact`, `./lr 7`, and `./lr secrets`. For Python code changes, prefer direct static checks. For drift-sensitive edits, run the relevant drift check.

### A4 post-edit adversarial challenge

Use the smallest validator set matching the changed risk surface. High-risk includes auth/session/CSRF/CORS/admin, billing/webhooks, storage/uploads/PDFs, assisted-submit/browser/CAPTCHA/2FA/rate-limit/user-review, privacy/redaction/logging, evidence integrity, DB/migration/runtime boundaries, native/frontend/build boundaries, broad cross-file patches, unclear test evidence, or any fix where validators disagree.

For every selected validator, use the registered subagent or the portable independent-review fallback, and require exact repo evidence. Never simulate missing validator findings.

### A5 code-edit final report

Respond with the mode-specific fields from the linked support docs. Include risk, threshold, patch-review file, files changed, scope kept, contracts preserved, focused tests, LR/drift/static checks, adversarial validation, Agent 5 audit, rebuttal, final patch decision, issues found, remaining risk, commands not run, and next safest validation.

## Mode C - Safe performance improvement workflow

Use this mode for scoped performance work with no behaviour change.

Hard gates:

- Correctness before speed.
- No public contract changes unless explicitly approved.
- No security/privacy/fail-closed weakening.
- No cache/concurrency/query/browser/provider optimization without proving safety.
- Run correctness validation before performance comparison.
- A faster broken path is a failed patch.
- Use `mode_c_performance.md` for the full checklist, safety checks, research-pack priority, and final report format.
- Use `main_auditor_research_pack.md` by default for safe optimization semantics.
- Use `research_link_pack.md` only for deeper cases such as SQLAlchemy query semantics, Playwright waits, Celery retries, Rust/native, security/cache/privacy, or provider docs.
- Use `mode_c_opposition_template.md` whenever Mode C escalates to selective/full A4 adversarial review.
- Repo truth still wins over external docs.

Mode C should remain narrow:

- no feature expansion
- no broad rewrites
- no test changes to fit the optimization
- no behaviour changes unless explicitly approved
- no long-running benchmarks unless repo evidence or the user requires them

## Mode B - Standalone bug-hunt workflow

Use this mode when the user asks for a bug hunt or audit without implementation.

- Canonical workflow and threshold rules live in `mode_b_main_auditor.md`.
- Report format and per-agent sections live in `opposition_template.md`.
- Official-doc research guidance lives in `research_link_pack.md` and `main_auditor_research_pack.md`.
- Validation command details live in `validation_commands.md`.

Core Mode B rules:

- Use `docs/bug_hunts/index.md` to find the active ledger volume.
- Keep one `docs/bug_hunts/opposition/BUG-YYYYMMDD-NNN-opposition.md` file per candidate.
- Keep each candidate's PoC and counter-tests under `docs/bug_hunts/poc/BUG-YYYYMMDD-NNN/`.
- Do not overwrite earlier evidence when a claim narrows; add a new file or versioned refinement.
- Write candidate entries in the active `bugs_found_N.md` and update `index.md` after every entry.
- Do not change app code or tests in standalone bug-hunt mode.
- If a PoC or counter-test is weak, record the weakness honestly rather than guessing.

Use the support docs for the details of repo-truth discovery, LR planning, folder-by-folder audit flow, PoC and staging gates, real subagent setup checks, B7 threshold selection, Agent 5's five-phase audit workflow, and main-auditor synthesis and rebuttal.

Hard gates that stay visible in this file:

- Mode A and Mode B are distinct; use the right mode for the task.
- Standalone bug-hunt mode does not change app code or tests.
- Independent subagents only; use the portable fallback when a registered reviewer is unavailable; never simulate opposing-agent or Agent 5 reviews.
- Timeout, skipped command, or missing dependency is not a pass.
- B7-lite, B7-selective, and full B7 are distinct thresholds; full B7 is required for high-risk candidates.
- Opposer 1 is mandatory for B7.
- Full B7 uses sequential spawn: all four opposers first, then Agent 5.
- Full B7 no-peeking: the main auditor does not read the opposition file until all five results exist.
- Agent 5 starts only after the required opposition sections are complete.
- A failing PoC is required before B7.
- Staging validation must confirm the PoC actually fails and is minimally scoped.
- After opposition, the main auditor must actively search for evidence that still supports the bug before concluding `Not a bug`.
- Downgrade is not disproval; a narrower real issue must be validated as `Validated downgraded bug`.
- BUG IDs stay stable and `index.md` remains the master hub.
- Approval remains threshold-aware: high-risk and contradictory candidates need the stronger path.

### Bug ledger entry lifecycle

- Statuses: Candidate, Under opposition, Validated bug, Validated downgraded bug, Not a bug, Accepted risk, Needs more evidence, Fixed.
- Keep IDs stable: `BUG-YYYYMMDD-NNN`.
- Do not delete old BUG entries; update them in place.
- Append rejected hypotheses to the rejected volume instead of erasing them.

### Opposition file lifecycle

- Create the temporary opposition file after the candidate entry exists.
- Collect all four opposition sections before Agent 5 starts when full B7 is required.
- Keep Agent 5's audit in the same opposition file.
- Delete the temporary opposition file after the final ledger update unless repo policy says to archive it.

### Severity model

If the repo does not define severity, use:

- P0 - critical correctness/security/privacy/data-loss/startup bug
- P1 - high-risk user-facing, payment, auth, storage, worker, or provider bug
- P2 - maintainability, regression, coverage, drift, or reliability bug
- P3 - low-risk bug, inconsistency, stale docs-with-risk, weak diagnostics, or follow-up improvement

Do not inflate severity, and do not downgrade security/privacy impact just because the fix is easy.

### Online research rules

Use official docs first when semantics matter. Prefer official docs, standards, and authoritative project docs over blogs or forum posts.

### Proposed fix rules

Any proposed fix must be scoped, preserve public contracts, avoid broad rewrites, avoid unrelated upgrades, and include tests or validation evidence.

### Final verification before documenting a validated bug

Confirm file paths exist, evidence is current, the PoC and counter-tests were run or honestly reported, the bug survived the selected threshold, real subagents were used, severity is honest, downgrade is not a disguised `Not a bug`, and no secrets are included.

### Final response format

Use the mode-specific report fields from the linked support docs. Keep the final answer compact and include:

- mode
- risk / severity
- threshold used
- opposition file
- bug report written
- validation used
- verdict
- remaining risk
- commands not run and why
- next safest action

## Mode D - Security assurance and hardening workflow

Use this mode for security posture review of a named surface. Mode D is security-first: it builds a threat model, verifies controls, identifies hardening opportunities, and proposes scoped hardening.

- Canonical lifecycle and threshold rules live in `mode_d_security_review.md`.
- Security Review artifact format lives in `security_review_template.md`.
- Three mandatory security research packs: `security_foundations_pack.md`, `security_testing_pack.md`, `security_controls_pack.md`.

### Two phases

**D-audit** — security analysis + threat model + control verification + reviewer opposition + evidence synthesis. No app code. No normal repo test changes. Scoped PoC/counter-tests live under `docs/security_reviews/poc/SEC-YYYYMMDD-NNN/`.

**D-hardening** — only after (a) D-audit approves a scoped hardening proposal AND (b) user approves implementation. D-hardening is a **Mode A run** scope-frozen to the proposal. Mode A owns the patch, regression tests, A4 patch-review oversight, and `lr secrets`/`lr impact`/`lr 7` gates.

### Mode D declaration

Every Mode D run starts with:

```text
BugGuard mode: Mode D - security assurance and hardening (D-audit)
Target surface:
D7 threshold: D7-lite / D7-selective / full D7
Security review file: docs/security_reviews/SEC-YYYYMMDD-NNN-review.md
Risk level: low / medium / high / contradictory
Research packs: security_foundations_pack.md + security_testing_pack.md + security_controls_pack.md (mandatory)
Reason: <one compact sentence>
```

### D7 thresholds

- **D7-lite**: main auditor + Opposer 1 + one specialist. Narrow single-control question, no security/privacy/fail-closed surface.
- **D7-selective**: main auditor + Opposer 1 + selected Opposer 2/3/4. Multi-control question, no cross-boundary failure mode. Agent 5 only if threshold policy declares it.
- **full D7**: main auditor + Opposers 1-4 + Agent 5. Mandatory for security/privacy/fail-closed, auth/session/CSRF/CORS/admin, billing/webhooks, storage/uploads/PDFs, assisted-submit/browser/CAPTCHA/2FA/final-submit, DB/migrations/runtime, provider/API, OAuth, email/provider integrations, SSRF/injection/path-traversal/deserialization, retries/idempotency, fail-open/fail-closed, cross-boundary, contradictory evidence, or when selected opposers disagree.

Because Mode D is security-first, most D runs land at full D7.

### Topology

1. Main auditor performs security analysis, writes posture sections only (target, assets, actors, entry points, data flows, trust boundaries, threat assumptions, existing controls, suspected weaknesses, evidence index, initial risk assessment, initial hardening proposal, research-pack usage).
2. Opposer 1 challenges exploitability, reproduction, attacker preconditions, claimed impact, PoC validity, realistic attack paths. Own PoC/counter-test. Own section.
3. Opposer 2 challenges using repo truth, contracts, middleware order, feature flags, deployment assumptions, caller/callee chains, existing controls. Own test. Own section.
4. Opposer 3 independently performs architecture/security/privacy opposition, trust-boundary/bypass analysis, privilege-transition, secondary effects, availability regression. Remains independent from the Mode D auditor despite shared security orientation. Own test. Own section.
5. Opposer 4 checks official standards, framework/provider/library semantics, version applicability, whether external guidance is incorrectly treated as repo proof. Own focused evidence test. Own section.
6. Agent 5 starts only after all required reviewer sections + test evidence exist (full D7 only). Reads all evidence, may run own evidence test, writes own section. Does not replace reviewers.
7. Main auditor reads all completed evidence, actively rebuts its original posture, resolves contradictions, performs per-concern decision, recommends transitions.

The main auditor must not write, paste, transcribe, summarize, or backfill reviewer-owned sections. General agent output is not a substitute for the Security Review artifact.

### Per-concern decision enum

D-audit produces a decision per surfaced concern:

- **Existing sufficient control** — nothing to do.
- **Hardening opportunity** — queued for D-hardening if user approves.
- **Vulnerability** — proven contract-violation; must transition to Mode B.
- **Accepted risk** — residual; documented with compensating controls and re-review date.
- **Needs more evidence** — inconclusive; SEC entry marked for re-audit.

### Mode D rules (hard gates visible in this file)

- D-audit does not change app code or normal repo tests.
- Independent subagents only; use the portable fallback when a registered reviewer is unavailable; never simulate opposing-agent or Agent 5 reviews.
- Timeout, skipped command, or missing dependency is not a pass.
- All three security packs are mandatory for every Mode D run; usage must be recorded.
- Opposer 1 is mandatory for every D7 candidate.
- Full D7 uses sequential spawn: all four opposers first, then Agent 5.
- Full D7 no-peeking: the main auditor does not read reviewer sections until all five results exist.
- Agent 5 starts only after required opposition sections are complete (full D7).
- The main auditor does not backfill reviewer sections.
- Vulnerability concerns route to Mode B, not self-validated in D.
- D-hardening is a Mode A run, not a D code-writing mode.
- Permanent regression tests require a Mode A transition.
- SEC IDs stay stable: `SEC-YYYYMMDD-NNN`.
- `docs/security_reviews/index.md` is the master navigation hub.
- External standards define expected properties; repo truth is the final authority.

### Mode D artifacts

- `docs/security_reviews/SEC-YYYYMMDD-NNN-review.md` — Security Review artifact.
- `docs/security_reviews/poc/SEC-YYYYMMDD-NNN/` — scoped PoC/counter-test artifacts.
- `docs/security_reviews/index.md` — navigation hub.
- `docs/bug_hunts/patch_reviews/PATCH-YYYYMMDD-NNN-review.md` — linked from SEC entry when D-hardening applies.
- `docs/bug_hunts/bugs_found/bugs_found_N.md` — receives the entry if D-audit → B transition occurs.

## Validation preference

For Python code changes, prefer direct static checks over `lr static`:

```bash
ruff format --check .
mypy app
pyright
```

Use `lr static`, `lr static --check`, full `lr 13`, or other long-running commands only if repo evidence or the user says they are required. When needed, run them into `.tmp/validation/` logs - never wait on a live terminal tail.

## Approval gate

Bug-hunt mode: no app code/tests/env/migrations/baselines changed. No writer/apply LR command run. No live external calls. No secrets printed. Every validated bug survived its selected Mode B threshold, with Opposer 1 mandatory for B7 and full B7 required for high-risk/P0/P1/P2/security/privacy/fail-closed/cross-boundary/contradictory candidates. Report is documentation only. Approve before implementation.

Code-edit mode: all changes checked against approved scope. Tests/LR checks run or honestly reported. High-risk edits received adversarial review. No new bugs hidden. No secrets printed. Approve before merge.

Mode D (D-audit): no app code/tests/env/migrations/baselines changed. No writer/apply LR command run. No live external calls. No secrets printed. All three security packs consulted with usage recorded. Every concern classified honestly (sufficient control / hardening / vulnerability / accepted risk / needs more evidence). Vulnerability concerns transitioned to Mode B. Hardening proposals queued for D-hardening (Mode A) with user approval. Report is documentation only. Approve before implementation.
