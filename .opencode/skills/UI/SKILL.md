---
name: UI
description: Use this skill for any rendered-UI quality, accessibility, responsive layout, CSS architecture, design-system consistency, component-state, visual-regression, or visual-polish task. It runs a surface-evidence pipeline with mandatory design-language inference, typed audit modes, evidence tiers, structured opposition, and BugGuard boundary enforcement before any implementation. Do not use for correctness/business-logic changes (hand to BugGuard), for LR drift (audit-lr-drift), or for repo-context hygiene (repo-context-curator).
---

# UI Skill

## Purpose

This skill treats UI quality as a rendered-surface evidence system, not a multi-agent debate.

The core object is the **UI Surface Evidence Model** — route/template/component graph, design tokens, CSS architecture, rendered screenshots, viewport matrix, state matrix, interaction matrix, accessibility signals, DOM/CSS cascade risks, inferred design language, constraints, proposed change set, validation evidence, and an opposition report.

A bug in code can often be traced to a file and a test. UI quality exists in the rendered result: layout, spacing, focus states, typography, motion, responsive breakpoints, density, hierarchy, colour relationships, and interaction feedback. So this skill requires rendered evidence (Tier 2+) before high-confidence design claims, and forbids confident claims from prompt-only or code-only evidence (Tier 0/1).

## Trigger conditions

Use this skill whenever an agent is about to:

- change markup, templates, CSS, component structure, or visual assets
- add/alter styling systems (Tailwind config, Bootstrap variables, CSS custom properties, SCSS, CSS Modules, CSS-in-JS)
- fix a visual, responsive, layout, spacing, typography, colour, or motion problem
- audit or improve accessibility of a UI surface
- clean up CSS architecture (cascade, specificity, tokens, layers)
- improve component states (hover/focus/active/disabled/loading/empty/error)
- match a screenshot or implement a design
- audit a whole UI surface for visual debt

Always trigger for externally-facing or high-regret UI surfaces: public forms, claims/submit flows, auth pages, dashboards, admin tables, modals/dialogs, email-rendered templates, and printable/refund document templates.

## Non-negotiable rules

Never:

- implement before surface discovery and design-language inference are done
- introduce a new visual language unless explicitly requested
- restyle the product globally from one screen
- replace a design system with ad hoc CSS
- add animation without checking reduced-motion handling
- add new colours outside the token system unless creating tokens is part of the task
- improve layout by changing content hierarchy or business behaviour
- touch validation/business logic (hand to BugGuard)
- introduce new dependencies for visual polish unless explicitly justified
- make high-confidence design claims from Tier 0 (prompt-only) or Tier 1 (code-only) evidence
- ignore the BugGuard boundary (see `core/bugguard-boundary.md`)
- simulate or self-write opposition reviews (use real subagents or honestly report an orchestration gap)
- treat an automated accessibility scan as proof of accessibility (it is partial coverage)
- say "looks better" in a report — report change against existing tokens/state/viewport evidence
- change production visual baselines unless explicitly allowed

## Core principle

Every change and every UI claim must survive this question:

```text
What rendered evidence proves this change preserves the existing product language and fixes a real defect?
```

Evidence tiers (defined in `core/evidence-model.md`):

| Tier | Evidence | Confidence allowed |
|---|---|---|
| 0 | inferred from prompt only | Speculative only |
| 1 | code/static files inspected | Low |
| 2 | rendered screenshots inspected | Medium |
| 3 | interactive browser flow inspected | High (with comment) |
| 4 | cross-viewport/theme/state validation | High |
| 5 | CI-backed visual/accessibility checks | High |

Do not implement from Speculative or Low evidence unless the user explicitly accepts the risk.

## Modes

The skill separates **audit mode** from **implementation mode**. It must not assume implementation.

| Mode | Behaviour |
|---|---|
| `audit only` | produce report + change plan; edit nothing |
| `audit + patch` | audit, then implement only accepted, smallest-safe changes |
| `visual polish` | scoped beautification inside existing language |
| `css architecture` | cascade/specificity/tokens/layers; no visual redesign |
| `responsive fix` | viewport/container behaviour |
| `accessibility fix` | WCAG/APG/semantics/keyboard |
| `design-system cleanup` | token consolidation; no new language |
| `component state improvement` | hover/focus/active/disabled/loading/empty/error/success |
| `full surface refinement` | whole-surface visual-debt pass |
| `implement design` | design-language compatibility + visual validation |
| `match screenshot` | screenshot evidence + visual diff + anti-hallucination |

Mode is chosen at Stage 0 (Request classification) and may only narrow later.

## Workflow (16 stages)

```text
0.  Request classification (task type, stack, surface size, evidence availability)
1.  Surface discovery
2.  Stack + styling-system detection
3.  Design-language inference
4.  Evidence capture
5.  Research-pack routing
6.  UI audit
7.  Issue triage
8.  Change-plan generation
9.  Opposition review
10. Synthesis + scoped implementation plan
11. Implementation
12. Rendered validation
13. Accessibility/interaction validation
14. CSS architecture validation
15. Final UI report
```

Detailed stage definitions live in `core/`. Files are named after their owner stage.

## Agent topology (escalation, not default-many)

Default topology:

```text
Orchestrator
├─ Surface Mapper
├─ Design-Language Extractor
├─ UI Auditor
├─ Opposition Critic
└─ Implementer/Validator
```

Specialist topology (escalated only when the surface needs it):

```text
Orchestrator
├─ Surface Mapper
├─ Design-Language Extractor
├─ CSS Architect
├─ Accessibility Specialist
├─ Responsive/Layout Specialist
├─ Interaction Specialist
├─ Visual Consistency Critic
├─ Regression Boundary Critic
└─ Implementer/Validator
```

Full opposition is **escalated, not default**. Use the smallest critic set that covers the change.

## Support files

Read the file for the stage you are working on. Do not load every file every run.

- `core/orchestrator.md` — routing, scope, mode transitions, handoff to BugGuard, final decision
- `core/surface-discovery.md` — surface map build rules, template/static inheritance
- `core/evidence-model.md` — evidence tiers, capture contract, hallucination guards
- `core/design-language-inference.md` — mandatory design-language extraction, anti-generic constraints
- `core/audit-taxonomy.md` — typed audit modes, issue schema, severity, visual-debt taxonomy
- `core/implementation-rules.md` — patch rules, CSS change hierarchy, UI budget
- `core/validation-rules.md` — static/render/accessibility/interaction/performance validation
- `core/opposition-rules.md` — deterministic opposition checklist and output decisions
- `core/bugguard-boundary.md` — what UI may/must not own

Packs, schemas, templates, adapters, and examples live in their own folders. See `README.md` for the catalogue.

## Generated project artifacts

For an audited surface, write under a repo-local `.ui/` root (configurable). Required:

```text
.ui/
  surface-map.json
  design-language.md
  reports/
    ui-audit.md
    ui-opposition-report.md
    ui-validation-report.md
  evidence/
    screenshots/{before,after,diff}/
    accessibility/
    css/
    traces/
```

Optional: `accessibility-scan.json`, `css-architecture-report.json`, `token-inventory.json`, `component-state-matrix.json`, `responsive-matrix.json`, `manual-checklist.md`, `rollback-plan.md`, `ui-implementation-notes.md`, `ui-change-plan.md`.

Do not write `.ui/` into the repo unless the surface is being audited/changed. Do not commit screenshots/that contain user data.

## BugGuard boundary

UI may change markup structure for semantics, CSS, visual component composition, accessible labels, and non-business interaction affordances.

UI must **not** own: validation correctness, auth/security, business rules, data fetching, performance-sensitive algorithms, regression-test truth. See `core/bugguard-boundary.md`. When a UI change exposes a correctness bug, hand to BugGuard; do not fix it inline.

## Completion requirement

Once this skill is invoked for a task, it must complete its selected stages. Do not stop mid-pipeline and declare a pass.

- Do not skip design-language inference before proposing visual changes.
- Do not skip opposition when the change is high-regret or design-system-altering.
- A reviewer only counts when its finding is durably captured in `ui-opposition-report.md`.
- Do not mark an issue `accepted`/`fixed` without rendered validation for the touched surface.
- Report incomplete stages as incomplete; do not paper over orchestration gaps with self-written opposition.

## Severity model

- **Critical** — inaccessible / unusable / broken layout
- **High** — major visual or interaction quality problem
- **Medium** — inconsistency or polish issue users notice
- **Low** — minor refinement
- **Deferred** — valid but outside current scope
- **Blocked** — unsafe or inconsistent with design language

Do not inflate severity. Do not downgrade accessibility/layout impact because the fix is easy.

## Confidence labels

Every recommendation carries a confidence label:

- **High** — code + rendered evidence + validation
- **Medium** — code + partial render evidence
- **Low** — code only
- **Speculative** — prompt only

The skill avoids implementing Speculative changes.

## Final report

Use the template in `templates/ui-report.md`. Reports must state the change against existing tokens/state/viewport — never "looks better".