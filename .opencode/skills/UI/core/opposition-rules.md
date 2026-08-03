# Core — Opposition Rules

Stage 9. Opposition is deterministic, not conversational "another agent's opinion".

## Inputs

Opposition reads:

- `surface-map.json`
- `design-language.md`
- `ui-audit.json` / `ui-audit.md`
- `ui-change-plan.md`
- evidence bundle under `evidence/`

## Attack surfaces (fixed checklist)

Each proposed change is challenged on each applicable surface:

1. **Visual consistency** — Is the issue real from evidence? Is the fix consistent with existing design language?
2. **Accessibility** — Does the fix break accessibility? Does it add motion without reduced-motion handling? Does it remove semantics?
3. **CSS architecture** — Does it increase specificity, add `!important`, leak outside scope, bypass tokens?
4. **Responsive / layout** — Overfit to one viewport? Overflow risk? Container behaviour?
5. **Scope / regression** — Touches BugGuard-owned correctness/logic? Wider than necessary? Hidden coupling?
6. **Smaller-fix** — Is there a smaller, safer fix at the same effect?

The critic set used is the escalation chosen at Stage 0 (see `orchestrator.md`). Do not run every critic for every change; do run all applicable checks within the chosen set.

## Deterministic challenges per change

For each proposed change, opposition produces zero or more findings. Each finding:

```text
Finding id: OPP-003
Proposed change: <summary>
Challenge surface: <visual consistency | accessibility | css architecture | responsive | scope | smaller-fix>
Decision: ACCEPT | ACCEPT WITH MODIFICATION | BLOCK | DEFER | NEEDS EVIDENCE | HAND OFF TO BUGGUARD
Reason: <one or two sentences, citing surface-map/design-language/evidence>
Safer alternative: <if decision is not ACCEPT>
Evidence cited: <paths to evidence bundle rows>
```

## Decisions

- **ACCEPT** — change proceeds as proposed.
- **ACCEPT WITH MODIFICATION** — change proceeds with the stated safer alternative. The change plan is updated; the modification is reflected in synthesis.
- **BLOCK** — change is rejected. Reason must name the violated constraint (design language, accessibility, scope, etc.).
- **DEFER** — valid but outside scope; record in report's "Remaining recommendations — Later".
- **NEEDS EVIDENCE** — current evidence tier is below required; do not implement until capture is upgraded.
- **HAND OFF TO BUGGUARD** — change exposes or requires a correctness/business/auth/perf fix; route to BugGuard; UI stops.

## Worked example

```text
Finding OPP-003
Proposed change: Increase all card padding from 16px to 28px.
Challenge surface: visual consistency
Decision: BLOCK
Reason: The product uses compact admin density. 28px appears only on marketing sections. This reduces table scanability and creates inconsistent density.
Safer alternative: Use existing --space-5 only on the empty-state card, not all cards.
Evidence cited: design-language.md (density: compact), screenshots/dashboard-default-1280.png
```

## Artifact ownership

- Opposition findings are written into `reports/ui-opposition-report.md` (template: `templates/ui-opposition-report.md`).
- Each critic writes its own findings section. The orchestrator/main auditor does not backfill or summarize critic sections in place of the critic writing them.
- If a critic cannot write its section, mark opposition `incomplete` and report the orchestration gap; do not self-write the review.
- Real subagents only where the topology uses them. The default Opposition Critic is one reviewer. Specialist topology uses multiple. Never simulate.

## When opposition is required

- High or Critical severity changes: full applicable critic set.
- Design-system-altering changes: full applicable critic set.
- Changes touching custom widgets: accessibility critic mandatory.
- Changes touching responsive layout: responsive critic mandatory.
- Single Low-severity polish inside one component with low regression_risk: the single Opposition Critic suffices.

## Final synthesis dependence

Stage 10 synthesis begins only after the required opposition sections exist. A missing critic section blocks synthesis; report `incomplete` rather than papering over.