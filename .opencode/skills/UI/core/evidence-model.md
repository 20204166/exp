# Core — Evidence Model

Stage 4. UI quality exists in the rendered result. This file defines the evidence tiers, the capture contract, and the hallucination guards that prevent confident claims from weak evidence.

## Evidence tiers

| Tier | Evidence | Confidence label allowed |
|---|---|---|
| 0 | inferred from prompt only | Speculative |
| 1 | code/static files inspected | Low |
| 2 | rendered screenshots inspected | Medium |
| 3 | interactive browser flow inspected | High (with comment) |
| 4 | cross-viewport/theme/state validation | High |
| 5 | CI-backed visual/accessibility checks | High |

Hard rule: do not make high-confidence design/layout/spacing claims from Tier 0 or Tier 1 evidence.

Soft rule: a Tier 1 claim (code-only) about something verifiable from code — e.g. "this selector has specificity 0,3,0" — is acceptable as Low confidence. It becomes Medium only with rendered screenshots showing the effect.

## Capture contract

For every audited surface, capture:

- code evidence — template/component sources, CSS sources, token references
- rendered screenshots — before; after; diff (only when changes are made)
- DOM excerpts — for landmark/heading/label/focus-order checks
- computed styles for key elements — padding, font-size, color, z-index, position
- accessibility tree signals — name/role/value, landmarks, heading order
- interaction traces — where possible (hover/focus/active/submit/error)
- viewport snapshots — across the project's viewport matrix
- theme snapshots — light/dark/hc when the product has themes

Do not capture user data. Screenshots of forms with real user input are forbidden. Use synthetic fixtures.

## Evidence directory layout

Per surface, under `.ui/<surface-slug>/evidence/`:

```text
screenshots/
  before/<viewport>-<state>.png
  after/<viewport>-<state>.png
  diff/<viewport>-<state>.png
accessibility/
  axe-<viewport>-<state>.json
  keyboard-trace.md
css/
  computed-styles-<selector>.json
  specificity-<id>.md
traces/
  interaction-<flow>.md
```

## Validation ≠ proof

- An automated accessibility scan (axe/Lighthouse) is partial coverage, not proof of accessibility.
- Playwright visual comparison is rendered-evidence support, not a guarantee that the change is visually correct.
- Keyboard-only walkthrough is required (Stage 13) for accessibility fixes; automation alone is insufficient.

## Hallucination guards

Do not:

- describe a rendered state you did not capture (if you did not screenshot the 375px error state, do not describe it)
- claim a token exists without grepping the token source
- claim a component/element will behave the same after the change without capturing before/after evidence at the same tier
- claim a fix "preserves the existing language" without recording which token/rhythm/pattern it reused
- invent screenshots, DOM excerpts, or accessibility tree results
- extrapolate from one viewport to all viewports

If a capture is impossible (no renderable surface, no browser automation), record evidence tier honestly as `code only` and cap confidence at Low. Do not implement from Low confidence for high-regret surfaces unless the user accepts explicitly.

## Anti-generic-AI gate

The `packs/anti-patterns/generic-ai-ui.md` pack is consulted at the evidence-capture stage to baseline existing visual decisions so that proposed changes can be checked against them. Do not infer "improvement" by comparison to a generic SaaS aesthetic; compare against the product's existing language captured here.

## When evidence is weak

If evidence cannot rise above Tier 1 for a layout/spacing/responsive claim:

- mark the issue `needs evidence`
- do not implement
- record the missing capture in the report
- do not record the issue as `fixed` later without Tier 2+ evidence

If the user explicitly accepts a low-evidence fix, record the acceptance and the residual risk in the report under "Known limitations".