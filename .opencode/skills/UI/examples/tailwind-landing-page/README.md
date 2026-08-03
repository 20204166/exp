# Worked example — Tailwind landing page (`/`)

A condensed reference run of the UI skill on a Tailwind v4 marketing landing page.

## Surface

Tailwind v4 marketing landing. Tailwind config + `@theme` overrides. Hero, feature grid (container-query-driven cards), CTA, header, footer. State matrix driven by image-load (loading / loaded / failed).

See `surface-map.json` and `design-language.md` for the artifacts.

## Mode path

`responsive fix` → user reported "feature grid cards look cramped at ~360px". Risk `medium` → default topology + Responsive Critic (escalated).

## Sample issue (Stage 6)

### UI-007 — Feature-grid card collapses awkwardly in narrow container

```json
{
  "id": "UI-007",
  "surface": "landing",
  "mode": "responsive fix",
  "category": "responsive",
  "severity": "medium",
  "confidence": "high",
  "evidence": [
    "screenshot: evidence/before/375-default.png (card inside FeatureGrid wraps title on 2 lines within 8px of icon)",
    "css: src/pages/Landing.tsx (FeatureGrid uses `grid-cols-1 md:grid-cols-3` but each card uses `gap-2` only)",
    "container: card lives inside a 340px wide @container ancestor"
  ],
  "design_language_fit": "container-queries supply the right mechanism; current implementation uses viewport breakpoint only, missing the container-specific behaviour",
  "user_impact": "title wraps awkwardly when its container is narrow even though viewport is wider (sidebar layouts, embeds)",
  "recommended_fix": "switch card grid gap to `gap-4` and rely on @container variants (@sm/@md) so cards reflow based on container, not viewport",
  "regression_risk": "low",
  "validation": ["375 + 768 + 1280 diffs", "340px container capture", "wrap-count comparison before/after"]
}
```

## Triage

- must fix: UI-007
- should fix: gap-[18px] drift (3 occurrences) — present but breaks separation; log separately
- defer: image-fail alt block (valid; touches BugGuard语义 surface)

## Sample opposition finding (Stage 9)

```text
Finding OPP-001
Proposed change: Replace viewport-only grid gap with gap-4 + @sm/@md container-query variants on the FeatureGrid cards.
Challenge surface: responsive
Decision: ACCEPT
Reason: Tailwind v4 container-query variants (@sm/@md) are native and already in use elsewhere in the surface (per design-language evidence E4). The proposal reuses theme.spacing.gap-4 instead of arbitrary gap-2. No new breakpoint outside theme.screens.
Evidence cited: design-language.md (must_reuse @container utilities, must_preserve container-query-driven cards), src/styles/globals.css:18 (@container utilities in use), before/375-default.png.
```

Synthesis accepted as proposed; no modifications.

## Synthesised plan (Stage 10)

1. **UI-007** — accept as proposed. Files: `src/pages/Landing.tsx` (FeatureGrid block) + verify `@container` ancestor. Change card grid container to use `gap-4` and add `@sm:grid-cols-2 @md:grid-cols-3` (reuse existing container-query variants). Validation: 375, 768, 1280 diffs; 340px container capture showing cards reflow.

## Final report excerpt (Stage 15)

> Feature-grid cards now reflow based on container width via Tailwind v4 `@sm`/`@md` variants, with `gap-4` from `theme.spacing`. The awkward 2-line title-wrap observed in the 340px container no longer occurs. No new breakpoints outside `theme.screens`; no new tokens or dependencies. The deferred image-fail alt block is BugGuard territory and is logged for follow-up.

## What this example is for

Shows the responsive-fix mode: a defect that depends on container width rather than viewport width, where the change uses Tailwind's native container-query variants rather than minting arbitrary media queries. The audit explicitly distinguishes viewport-driven layout (app shell) from container-driven layout (FeatureGrid cards), which is the key Tailwind modern-vs-legacy distinction.