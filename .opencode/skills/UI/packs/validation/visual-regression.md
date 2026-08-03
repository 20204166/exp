---
pack: validation.visual-regression
version: 2026-07
authorities:
  - Playwright visual comparisons
  - Storybook test-runner / chromatic where used
load_when:
  - implementation
  - match screenshot task
  - visual polish with sensitive layout
rules:
  - Visual regression compares rendered screenshots against a reference
  - Reference baseline is production truth — do not update baseline silently; update only with explicit user approval
  - Use project-specific viewport matrix, not a single desktop shot
  - Capture state matrix (default, error, loading, focus-visible where applicable) not just default
  - Diff threshold set per project; 0 diff is the goal, controlled tolerance is acceptable
validation_checks:
  - before/after screenshots at each viewport x state
  - diff pixel ratio below threshold
  - no unintended regressions on surfaces outside the touched scope
false_positives:
  - font-loading snapshot variance -> stabilize via font-display and wait-for-fonts
  - dynamic content -> mock deterministically
  - flaky animations -> disable motion or wait for settle
anti-patterns:
  - single-viewport assert as full validation
  - auto-updating baseline to "fix" a failing diff
report_snippets:
  - "Visual diff: N viewports x M states; max diff 0.04% on touched surface; 0 regressions outside touched scope"
framework_notes:
  - Storybook is a complement for component-level isolation; Playwright for full-surface flows
  - The UI skill creates/updates baselines only when explicitly allowed; otherwise it generates diffs for review
---

# Pack: Visual regression testing

Visual regression testing compares rendered screenshots against references. It is most natural with Playwright visual comparisons; Storybook test-runner / Chromatic can complement for component-level isolation.

Key principle: this skill does not auto-update baselines as a "fix." A failing diff means either a real regression or a deliberate change — distinguish the two in the report and require explicit user approval to update a baseline.

Coverage matters: a single desktop default-state diff is not visual regression. Use the project's viewport matrix and at least default / error / loading states for touched interactive components. Font loading and dynamic content introduce noise; stabilize with `font-display`, wait-for-fonts, deterministic mocks, and disabling motion during capture.