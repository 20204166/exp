# Core — Implementation Rules

Stage 11. Implementation only begins after Stage 10 synthesis, only for accepted/modified changes, and only with the smallest safe change.

## Implementation contract

1. Never start by editing.
2. Build surface map (Stage 1).
3. Infer design language (Stage 3).
4. Identify smallest valuable issue set (Stage 7).
5. Write change plan (Stage 8).
6. Run opposition (Stage 9).
7. Synthesize (Stage 10).
8. Implement only accepted changes.
9. Validate rendered result (Stages 12–14).
10. Produce report (Stage 15).

Skipping straight to editing is a non-negotiable violation.

## Patch rules

- Prefer existing tokens over new values.
- Prefer existing components over new ones.
- Prefer local fixes over global rewrites.
- Prefer semantic HTML over ARIA where native HTML works.
- Prefer CSS simplification over more wrappers.
- Prefer reducing inconsistency over adding decoration.
- Prefer one source of truth for spacing/colour/type.
- Avoid new dependencies.
- Avoid broad resets.
- Avoid touching business logic (BugGuard boundary).
- Avoid hidden layout coupling (a local change that silently shifts another surface).
- Avoid replacing a design system with ad hoc CSS.
- Avoid introducing animation without reduced-motion handling.
- Avoid new colours outside the token system unless creating tokens is part of the task.

## CSS change hierarchy

Apply changes in order; stop at the first option that fits.

1. Reuse existing class / component / token.
2. Add a missing token **only if a repeated pattern exists** (3+ call sites).
3. Add a component-local style.
4. Add a utility only if the project uses utilities (Tailwind/Bootstrap utility layers).
5. Add a global style only if the rule is truly global.
6. Add a cascade layer only as an intentional architecture migration (not a one-off override).
7. Add a dependency only with explicit justification in the change plan.

Jumping steps (e.g. adding a new dependency to fix padding) is a violation.

## UI budget

Treat UI architecture like a perf budget. Per changelist, the following must not regress unless explicitly justified in the change plan and accepted by opposition:

```text
max new hardcoded colours: 0
max new arbitrary spacing values: 0
max new !important: 0
max specificity increase: none without reason
max new global selectors: 0
max new dependencies: 0 unless justified
min viewport coverage: 3 (must include smallest, mid, largest target)
min state coverage: default / error / loading / focus-visible for touched interactive components
```

A "0" budget is not a target — it is a ceiling. Exceeding it requires an accepted justification in the change plan.

## Smallest-safe-change

For each accepted issue, implement the smallest change that resolves the defect and preserves:

- existing token usage
- existing component language
- existing density and rhythm
- existing focus-visible behaviour
- existing reduced-motion behaviour
- existing responsive behaviour
- existing state coverage (do not remove a state to add one)

If a fix would require widening scope, return to Stage 8 and re-plan. Do not widen silently.

## No-redesign principle

Default behaviour is **polish the existing product**, not redesign it. A redesign requires explicit user request and the `implement design` mode. Even then, the report must document the design language being superseded.

Do not "improve" layout by changing content hierarchy or business behaviour. If the business behaviour is wrong, route to BugGuard.

## Rollback

Every accepted change with `regression_risk` medium or higher must include a rollback note in `reports/ui-change-plan.md`. A rollback note names the files touched and the prior values; it is not a git revert instruction.

## What implementation must not do

- Edit beyond the accepted change list.
- Edit templates/CSS that the surface map does not include without re-running discovery.
- Add files that widen the surface without re-running Stage 1 and Stage 3.
- Run writer/apply LR commands unless the task is explicitly an implementation task.
- Print secrets, env values, user data, URLs containing identifiers.