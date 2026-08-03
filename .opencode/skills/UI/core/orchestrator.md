# Core — Orchestrator

The orchestrator owns Stage 0 (request classification), routing across stages, mode transitions, handoff to BugGuard, and the final synthesis decision (Stage 10). It never edits templates/CSS directly during audit mode.

## Stage 0 — Request classification

Before any discovery, classify and record:

```text
task_type: audit only / audit + patch / visual polish / css architecture /
           responsive fix / accessibility fix / design-system cleanup /
           component state improvement / full surface refinement /
           implement design / match screenshot
stack: react / vue / jinja / django / flask / fastapi / tailwind /
       bootstrap / vanilla css / css modules / scss / css-in-js / unknown
surface_size: single component / single page / multi-page surface / whole app
evidence_availability: code only / renderable / browser-automatable / ci-backed
mode: <one of the modes listed in SKILL.md>
risk: low / medium / high / design-system-altering
```

Write this header into `.ui/<surface-slug>/reports/ui-audit.md` before any other work.

### Routing decisions

The chosen `task_type` fixes the required stages and packs:

| task_type | Mandatory stages | Mandatory packs |
|---|---|---|
| audit only | 1,2,3,4,6,7,8,15 | design-language + audit-taxonomy |
| audit + patch | all | design-language + audit-taxonomy + implementation-rules |
| visual polish | 1,3,4,6,7,8,11,12,15 | design-language + `anti-patterns/generic-ai-ui` |
| css architecture | 1,2,4,6,7,8,11,14,15 | css/cascade + css/tokens + css/specificity |
| responsive fix | 1,2,4,6,7,8,11,12,15 | css/responsive + design-systems/spacing |
| accessibility fix | 1,2,4,6,7,8,11,13,15 | accessibility/* + validation/keyboard |
| design-system cleanup | 1,2,3,4,6,7,8,11,14,15 | css/tokens + design-systems/* |
| component state improvement | 1,3,4,6,7,8,11,12,13,15 | design-systems/component-anatomy + audit-taxonomy |
| full surface refinement | all | all relevant packs via Stage 5 routing |
| implement design | 1,3,4,8,11,12,15 | design-language + anti-patterns/generic-ai-ui |
| match screenshot | 1,4,8,11,12,15 | validation/visual-regression + anti-patterns/generic-ai-ui |

Skipping a mandatory stage is an orchestration gap, not an optimization. Report it honestly.

### Surface size → escalation

| surface_size | Default topology | Escalate to specialist when |
|---|---|---|
| single component | Orchestrator + Surface Mapper + Design-Language Extractor + UI Auditor + Opposition Critic | component exposes custom widget/accessibility risk |
| single page | default + Visual Consistency Critic | page contains custom widget, table, or modal |
| multi-page surface | default + Visual Consistency Critic + Regression Boundary Critic | surface spans auth/admin/billing or design-system boundaries |
| whole app | default + all specialists for sampled surfaces | sampling reveals cross-surface drift |

Full specialist topology is escalated, not default. Do not spin every specialist for a one-button padding fix.

### Risk → validation ceiling

| risk | Required validation minimum |
|---|---| 
| low | static + render before/after |
| medium | static + render + target viewports + a11y automated scan |
| high | static + render + full viewport matrix + a11y scan + keyboard walkthrough + opposition |
| design-system-altering | high + opposition + token-drift check + rollback plan |

## Mode transitions

A mode may only narrow. A transition is explicit and recorded:

```text
Mode transition:
From:
To:
Trigger evidence:
Reason:
Scope impact:
Artifacts carried forward:
Validation reset needed: yes/no
User approval needed: yes/no
```

Allowed transitions:

- `audit only` → `audit + patch`: only after user approval; do not silently start editing.
- `audit + patch` → `audit only`: when opposition blocks and the safe residual set is empty; report and stop.
- any → `implement design`: only with explicit user request; design-language inference stays mandatory.
- any → handoff to BugGuard: when a UI change exposes correctness/business/auth/perf behaviour. UI stops editing; BugGuard owns the correctness fix. UI may resume after BugGuard confirms.

A transition is not a validation result. The new mode must still complete its own required stages.

## Stage 10 — Synthesis

After opposition (Stage 9), the orchestrator decides per proposed change:

- **accepted** — implement as proposed
- **modified** — implement with the opposition's safer alternative
- **rejected** — drop; record why in the report
- **deferred** — valid but outside current scope
- **blocked** — unsafe, inconsistent, or BugGuard-owned
- **needs evidence** — Tier < required; do not implement until evidence captured
- **BugGuard handoff** — correctness/business/auth/perf surface; route to BugGuard

Synthesis output is `reports/ui-change-plan.md` (from `templates/ui-change-plan.md`).

## Production-readiness gates

Before the final report (Stage 15), the orchestrator confirms each required gate passed. Gates and their required evidence are defined in `validation-rules.md`. The orchestrator only marks a gate passed when the validation artifact contains the evidence.

Required gates (all modes unless audit-only with no patch):

1. Surface gate — whole surface inspected, not only one file.
2. Design-language gate — change preserves inferred product language.
3. Scope gate — no BugGuard-owned changes.
4. Accessibility gate — keyboard/focus/semantics checks pass for touched controls.
5. Responsive gate — touched surfaces pass target viewport checks.
6. CSS architecture gate — specificity, hardcoded values, global leakage no worse.
7. Visual evidence gate — before/after screenshots support the claim.
8. Opposition gate — risky proposals challenged and resolved.

Audit-only mode omits gates 3 and 7 but still runs 1, 2, 4, 5, 6, 8.

## Final report ownership

The final report uses `templates/ui-report.md`. The orchestrator writes the report only after required stages and opposition artifacts exist. Do not backfill opposition sections; if a critic cannot write its section, mark the report incomplete.