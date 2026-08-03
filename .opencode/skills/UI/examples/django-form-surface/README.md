# Worked example — Django form surface (`/claims/new`)

This is a condensed reference run of the UI skill on a Django-rendered refund claim form, intended to show how the artifacts fit together. It is illustrative; do not treat it as a finished audit.

## Surface

A compact, enterprise utility form (`/claims/new`). Stack: Django templates + django-crispy-forms. Server-rendered states: default / validation-error / loading / submit-success / permission-denied.

See `surface-map.json` and `design-language.md` in this folder for the Stage 1 and Stage 3 artifacts.

## Mode path

`audit + patch` → user explicitly approved implementation after audit. Risk `medium` → default topology + Visual Consistency Critic (escalated).

## Sample issues (Stage 6)

### UI-014 — Spacing between field groups in error state

```json
{
  "id": "UI-014",
  "surface": "claims/new",
  "mode": "audit + patch",
  "category": "spacing",
  "severity": "medium",
  "confidence": "high",
  "evidence": [
    "screenshot: evidence/before/375-validation-error.png",
    "css: static/css/forms.css:78 (form-group--error gap)",
    "dom: field group block"
  ],
  "design_language_fit": "violates existing 8px (--space-2) rhythm in error states only, where a 4px gap is used",
  "user_impact": "validation errors are dense enough to be hard to scan on mobile",
  "recommended_fix": "use --space-2 in error state to match default gap; do not introduce a new token",
  "regression_risk": "low",
  "validation": ["375 validation-error screenshot diff", "1280 validation-error screenshot diff", "keyboard trace to the first error"]
}
```

### UI-015 — Stepper hidden at 375 without alternative affordance

```json
{
  "id": "UI-015",
  "surface": "claims/new",
  "mode": "audit + patch",
  "category": "responsive",
  "severity": "high",
  "confidence": "high",
  "evidence": [
    "screenshot: evidence/before/375-default.png (stepper visible=no)",
    "css: static/css/forms.css:122 (@media max-width: 767px hide .progress-stepper)",
    "dom: stepper <ol> present but display:none"
  ],
  "design_language_fit": "removes existing visible progress hierarchy on mobile; occupies a precious mobile affordance without replacement",
  "user_impact": "mobile users lose sense of progress through a 4-step form",
  "recommended_fix": "render a compact horizontal step indicator with aria-current; reuse --space-2 / --radius-md; do not introduce a new widget",
  "regression_risk": "medium",
  "validation": ["375 default + step-2 vs step-4 diff", "keyboard trace through stepper buttons", "aria-current announced on step change"]
}
```

## Triage (Stage 7)

- must fix: UI-015 (high-severity, accessibility-adjacent)
- should fix: UI-014 (medium, low regression risk)
- defer: nick of `submit-success` empty-state illustration (valid, outside scope)
- do not touch: form validation rules (`is_valid()` semantics → BugGuard)

## Sample opposition finding (Stage 9)

```text
Finding OPP-001
Proposed change: Add a horizontal mobile-only step indicator that replaces the hidden .progress-stepper.
Challenge surface: visual consistency
Decision: ACCEPT WITH MODIFICATION
Reason: Reusing --space-2 and --radius-md is consistent with the design language; but the initial proposal used a custom grid of dots. Use existing .stepper-dots macro from static/css/forms.css:145 (already in use on wizard variants of the form) instead of minting a new widget.
Safer alternative: Reuse the existing .stepper-dots macro. Add aria-current to the active step. No new CSS selector.
Evidence cited: design-language.md (must_reuse --space-2, --radius-md), `static/css/forms.css:145` (.stepper-dots already exists but is unused on this surface).
```

## Synthesised change plan (Stage 10)

1. **UI-014** — accept as proposed: replace the 4px error-state gap with `--space-2`. Files touched: `static/css/forms.css:78`. Validation: 375 + 1280 validation-error diff; keyboard trace unchanged.
2. **UI-015** — modified: use existing `.stepper-dots` macro for mobile, add `aria-current="step"`. Files touched: `templates/claims/_progress_stepper.html`, `static/css/forms.css` (add container-query-friendly mobile stylesheet if needed; otherwise a media-query block matching the existing breakpoint tokens). Validation: 375 + 1280 diff at step-1/step-3; keyboard trace through stepper; aria-current announcement.
3. **submit-success illustration** — defer to Later in report.

## Final report excerpt (Stage 15)

> The mobile form now exposes a horizontal step indicator that reuses the existing `.stepper-dots` macro and `--space-2`/`--radius-md` tokens, restoring progress affordance at 375px without introducing a new widget. The validation-error state now uses the existing 8px rhythm (`--space-2`) instead of a one-off 4px gap. No new tokens, gradients, shadows, components, or dependencies introduced. No business logic touched; `is_valid()` semantics unchanged.

## What this example is for

A real run produces more evidence (more viewports, more states, more issues). This example shows the *shape* — surface-discovery respecting inheritance/includes, design-language inference yielding constraints, audit issues citing evidence and design-language effects, opposition forcing a safer alternative, and synthesis doing the smallest-safe-change with reuse-first CSS.