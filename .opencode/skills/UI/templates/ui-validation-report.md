# UI Validation Report — {surface}

Detailed Stage 12-14 validation record. The final `ui-report.md` summarises from this file. Conforms to `schemas/validation.schema.json` (machine-readable companion: `ui-validation.json`).

The orchestrator only marks a gate `passed` when this file contains the evidence. A skipped command, missing fixture, or unrenderable surface is **not** a pass — mark `incomplete` and list what was not run.

---

## Surface
- Slug: {slug}
- Mode: {mode}
- Risk: {low | medium | high | design-system-altering}
- Evidence level reached: {Tier 0..5}

## Stage 12 — Render validation

### Viewport x state coverage

| Viewport (CSS px) | default | error | loading | focus-visible | empty | other... |
|---|---|---|---|---|---|---|
| 320 | before/after/diff | | | | | |
| 375 | | | | | | |
| 768 | | | | | | |
| 1024 | | | | | | |
| 1280 | | | | | | |
| 1440 | | | | | | |

Minimum 3 viewports (smallest / mid / largest target) unless single-viewport surface.

### Container checks (where components live inside narrow containers)

| Container | viewport | overflow | horizontal scroll | clipped | notes |
|---|---|---|---|---|---|
| sidebar 240px | 1280 | y/n | y/n | y/n | |
| modal 480px | 1280 | | | | |
| table cell | 1024 | | | | |
| card 300px | 768 | | | | |

### Theme matrix (if product has themes)

| Theme | default | error | loading |
|---|---|---|---|
| light | | | |
| dark | | | |
| hc (if applicable) | | | |

### Render observations

- Overflow: {list any viewport/container with overflow}
- Horizontal scroll: {list}
- Font loading / layout shift: {observations}
- Visual diff max: {N}% on touched surface
- Regressions outside touched surface: {y/n + list}

## Stage 13 — Accessibility + interaction validation

### Automated a11y scan

- Tool: {axe-core / Lighthouse / equivalent}
- Output: `evidence/accessibility/axe-<viewport>-<state>.json`
- Findings: {count + brief}
- Note: automated scan is partial coverage, not proof of accessibility.

### Keyboard-only walkthrough

- Touched interactive controls: {list}
- Tab order: {verified / issues}
- Shift+Tab reverse: {verified}
- Enter / Space activates: {verified}
- Escape closes overlays: {verified}
- Focus returns to trigger on close: {verified}
- Trace: `evidence/accessibility/keyboard-trace.md`

### Focus-visible

- Contrast vs adjacent colours (>=3:1): {checked per state}
- Not obscured (WCAG 2.4.11): {checked}

### Landmarks / headings

- Landmarks: {header/nav/main/footer/aside — present per surface-map}
- Heading order: {no skips}
- Form labels: {every control has programmatic label}

### Contrast

- Text: {min ratio, pass/fail at 4.5:1 (3:1 large)}
- Non-text: {min ratio, pass/fail at 3:1}
- Focus indicator: {3:1 against adjacent colours — pass/fail}

### Reduced motion

- `prefers-reduced-motion` honoured: {y/n}
- Decorative transitions collapse to instant: {y/n}
- Essential state-conveying motion: {preserved semantically under reduced-motion}

### Interaction

- Trigger → feedback pairs audited: {list}
- Microinteractions without clear trigger flagged: {list (debt)}
- Modal open/close, escape, outside click: {verified}
- Toast / status message timing: {observations}
- Tab loop where appropriate: {verified}

## Stage 14 — CSS architecture validation

### Static checks

- Template syntax (lint): {result}
- CSS syntax (stylelint / parse): {result}
- Class references resolve: {result}
- Dead / unused style candidates: {findings}
- Specificity delta (touched files): before {highest} → after {highest}; {escalated?}
- New hardcoded colour values: {N}
- New arbitrary spacing values: {N}
- New `!important`: {N}
- New global selectors: {N}
- New dependency added: {y/n — name if yes}

### CSS architecture gates

- Specificity: {no escalation / escalated with accepted reason}
- Leakage: {no new selectors match outside touched component scope}
- Tokens: {no new hardcoded duplicates of existing tokens}
- Layers: {no new @layer / @layer added as intentional migration with note}
- `!important`: net count {not increased / increased with justification}

## Stage 14b — Performance boundary validation

(UI observed perf only; DOM/fetch/JS-execution semantics are BugGuard territory.)

- New layout shift: {y/n — describe}
- Expensive paint (large shadows / blurs / many backdrop-filters): {y/n}
- Animation jank (non-composited / long main-thread): {y/n}
- Unbounded shadows/filters: {y/n}
- `content-visibility` misuse: {y/n}
- Large icon/image regressions: {y/n}

Perceived-UI risks: {list}
BugGuard-perf handoffs: {list if any}

## Production-readiness gates

- [x / -] Surface gate — whole surface inspected
- [x / -] Design-language gate — change preserves inferred product language
- [x / -] Scope gate — no BugGuard-owned changes
- [x / -] Accessibility gate — keyboard/focus/semantics pass for touched controls
- [x / -] Responsive gate — touched surfaces pass target viewport checks
- [x / -] CSS architecture gate — specificity, hardcoded values, global leakage no worse
- [x / -] Visual evidence gate — before/after screenshots support the claim
- [x / -] Opposition gate — risky proposals challenged and resolved

(Audit-only mode omits scope and visual-evidence gates.)

## BugGuard boundary

- Touched correctness logic? {yes/no}
- Touched validation logic? {yes/no}
- Touched performance-sensitive path? {yes/no}
- Needs BugGuard follow-up? {yes/no — list handoff issue ids}

## Known limitations

- {commands not run and why}
- {evidence tiers that could not reach required level}
- {gates that remain incomplete}

## Conclusion

- Validation: {passed | failed | incomplete}
- Residual risks: {list}