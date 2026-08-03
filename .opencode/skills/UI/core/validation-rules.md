# Core — Validation Rules

Stages 12, 13, 14. Layered validation. Validation is evidence for the final report; it is not a pass/fail label alone.

## Stage 12 — Render validation

Captured evidence for the touched surface:

- before screenshots (per viewport × state)
- after screenshots (per viewport × state)
- visual diff
- viewport matrix coverage
- theme matrix (light/dark/hc when themes exist)
- state matrix coverage
- overflow checks (horizontal scroll, content clipped)
- font-loading checks (FOIT/FOUT, layout shift from web fonts)
- layout shift observation (CLS where measurable)

Default viewport matrix (narrow per project if documented):

```text
320, 375, 390, 414, 768, 1024, 1280, 1440, wide desktop
```

Minimum 3 viewports (smallest, mid, largest target) unless the surface is single-viewport (e.g. modal-only). Container-level behaviour is checked where the component lives inside narrow sidebars, cards, modals, tables, split panes — container queries exist because component layout often depends on container size, not only viewport.

## Stage 13 — Accessibility + interaction validation

### Accessibility validation

Minimum:

- automated scan (axe or equivalent) — partial coverage, not proof
- keyboard-only walkthrough for touched interactive controls
- focus-visible check
- focus order check
- landmark / heading check
- form label / error check
- reduced-motion check (the change must not add motion that ignores `prefers-reduced-motion`)
- contrast check (text + non-text contrast where applicable)
- screen-reader name/role/value spot checks

If the surface uses custom widgets (combobox, listbox, menu, tabs, accordion, dialog), the relevant APG keyboard model is required; consult `packs/accessibility/aria-apg-widgets.md`.

### Interaction validation

- hover / focus / active / disabled / loading / submit / error recovery
- modal open / close, escape key, outside click, focus trap when appropriate
- toast / status message timing
- tab loop where appropriate

Microinteractions are judged as **trigger → feedback** pairs (per NNGroup), not as decoration. A microinteraction without a clear trigger is debt, not polish.

## Stage 14 — CSS architecture validation

### Static validation

- template syntax (lint appropriate to stack)
- CSS syntax (stylelint if present; else parse check)
- class references resolve
- dead / unused style candidates
- specificity delta (compute before/after)
- new hardcoded colour / spacing values
- new `!important` usage
- new global selectors
- new dependency added

### CSS architecture gates

- specificity: highest selector specificity on touched files must not increase without a stated reason
- leakage: no new selectors that match outside the touched component scope (unless global style is intended and accepted)
- tokens: no new hardcoded values that duplicate existing tokens
- layers: introducing `@layer` requires an intentional migration note; not a default rewrite
- `!important`: net `!important` count must not increase

## Stage 14b — Performance boundary validation

BugGuard owns performance, but UI checks perceived-UI risk:

- new layout shift
- expensive paint-heavy effects (large box-shadows, blur filters, many backdrop-filters)
- animation jank (non-composited properties animated, long main-thread animations)
- unbounded shadows/filters
- `content-visibility` misuse
- large icon/image regressions

Findings here are reported as perceived-UI risk. Anything that changes DOM/fetch/JS execution semantics is BugGuard territory — report, do not fix.

## Validation report

Stage 15 input is `.ui/<surface-slug>/reports/ui-validation-report.md` (from `templates/ui-validation-report.md` or the validation section of `templates/ui-report.md`). Required blocks:

- viewport checks (per viewport × state)
- state checks
- accessibility checks (automated + manual)
- visual diff summary
- CSS architecture checks
- known limitations

## Do not fake a pass

- A skipped command, missing fixture, or unrenderable surface is not a pass.
- A dulled-down axe scan with no findings is not a pass for accessibility.
- Visual diff only on desktop default state is not a responsive pass.
- If validation cannot complete, the final report marks the gate `incomplete` and lists what was not run.