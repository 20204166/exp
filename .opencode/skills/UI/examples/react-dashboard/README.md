# Worked example — React dashboard (`/ops/dashboard`)

A condensed reference run of the UI skill on a React + CSS Modules operations dashboard.

## Surface

Tile-based operations console with a sidebar, filter chips, and metric tiles alternating with a trend chart. React 18 + CSS Modules, Storybook stories for `MetricTile` only.

See `surface-map.json` and `design-language.md` for the artifacts.

## Mode path

`visual polish` → user asked "tidy up the dashboard, it's starting to feel scattered". Risk `low` → default topology (single Opposition Critic). No specialist escalation.

## Sample issue (Stage 6)

### UI-003 — Hover scale on tiles introduces layout shift

```json
{
  "id": "UI-003",
  "surface": "ops-dashboard",
  "mode": "visual polish",
  "category": "interaction-feedback",
  "severity": "medium",
  "confidence": "high",
  "evidence": [
    "screenshot: evidence/before/1280-hover.png (neighbour tile shifted)",
    "css: src/components/MetricTile/MetricTile.module.css:42 (transform: scale(1.02) on :hover)",
    "interaction: hover trace shows 2px shift on adjacent tile"
  ],
  "design_language_fit": "violates composited-only transitions; scale affects layout, not just paint",
  "user_impact": "neighbouring tiles shift by 2px on hover; jittery feel over many tiles",
  "recommended_fix": "switch to elevation-only hover (existing --shadow-1 to --shadow-2 transition) using transform: translateY(-1px) with reduced-motion collapse; reuse --motion-fast",
  "regression_risk": "low",
  "validation": ["1280 hover diff", "reduced-motion reduced screenshot (no transform)", "neighbour tile no longer shifts"]
}
```

## Triage

- should fix: UI-003
- defer: replace spinners with skeletons on chart-load (valid but separate task)
- do not touch: dashboard fetch logic (`useDashboardData` retry timing → BugGuard)

## Sample opposition finding (Stage 9)

```text
Finding OPP-001
Proposed change: Replace hover scale with translateY(-1px) + --shadow-1 -> --shadow-2 transition.
Challenge surface: visual consistency
Decision: ACCEPT
Reason: Reuses --motion-fast and --shadow-2 (which already exists in tokens.module.css:23). Elevation-only movement does not affect layout. Composited properties only.
Evidence cited: design-language.md (must_preserve composited-only transitions, must_reuse --motion-fast), src/styles/tokens.module.css:23 (--shadow-2 already defined), evidence/before/1280-hover.png (shows 2px neighbour shift to remove).
```

## Synthesised plan (Stage 10)

1. **UI-003** — accept as proposed. Files: `src/components/MetricTile/MetricTile.module.css:42`. Replace `transform: scale(1.02)` with `transform: translateY(-1px)` transitioned over `--motion-fast`; add `box-shadow` transition from `--shadow-1` to `--shadow-2`. Add `@media (prefers-reduced-motion: reduce)` collapse to no transform / instant shadow. Validation: 1280 hover diff (neighbour tile no longer shifts); reduced-motion screenshot (no transform); keyboard focus-visible screenshot (focus indicator visible).

## Final report excerpt (Stage 15)

> Hover on metric tiles now elevates via translateY(-1px) with a `--shadow-1` to `--shadow-2` transition over `--motion-fast`, removing the 2px neighbour shift observed at 1280px. Reduced-motion users see an instant shadow transition with no transform. No new tokens or components introduced; `useDashboardData` and chart-load skeletons untouched.

## What this example is for

Shows the visual-polish mode: a small, focused defect (layout shift on hover) where the change reuses existing motion/elevation tokens, preserves the composited-only transitions rule, and touches one CSS Modules file. The BugGuard boundary is referenced for the chart-load path so the auditor does not sneak a perf change into a UI task.