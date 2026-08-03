# Worked example — Bootstrap admin (`/admin/users`)

A condensed reference run of the UI skill on a Bootstrap 5 admin user table.

## Surface

Bootstrap 5.2 admin with Sass overrides (`scss/_variables.scss`) and runtime CSS custom properties for `data-bs-theme="dark"` theming. Table renders server-side; row actions in Bootstrap dropdowns.

See `surface-map.json` and `design-language.md` for the artifacts.

## Mode path

`design-system cleanup` → user asked "the admin is showing its age, tidy the styles without redesigning". Risk `design-system-altering` → full applicable critic set (Visual Consistency + CSS Architecture + Scope/Regression + Smaller-Fix + default Opposition).

## Sample issues (Stage 6)

### UI-002 — Hardcoded `#1f4d8c` in table header

```json
{
  "id": "UI-002",
  "surface": "admin-users",
  "mode": "design-system cleanup",
  "category": "colour",
  "severity": "medium",
  "confidence": "high",
  "evidence": [
    "css: templates/admin/users.html:18 (style='background:#1f4d8c')",
    "css: scss/_variables.scss:8 ($primary = #1f4d8c)",
    "screenshot: evidence/before/1280-light.png (header colour appears consistent — duplicated via different sources)"
  ],
  "design_language_fit": "duplicates the $primary brand value as a hardcoded inline style; bypasses Sass variable system",
  "user_impact": "no visual impact today; maintainability debt: future $primary change will miss this row",
  "recommended_fix": "remove inline style; rely on .table-dark or a class derived from $primary",
  "regression_risk": "low",
  "validation": ["1280 light diff confirms same colour", "1280 dark-mode diff confirms same theme behaviour"]
}
```

### UI-005 — `.is-invalid` flashed then lost on Bootstrap form re-render

```json
{
  "id": "UI-005",
  "surface": "admin-users",
  "mode": "design-system cleanup",
  "category": "state",
  "severity": "high",
  "confidence": "high",
  "evidence": [
    "screenshot: evidence/before/768-search-failed.png (input red-bordered briefly)",
    "interaction: failed-search submit trace shows class lost after server re-render",
    "css: scss/_custom.scss:24 (.is-invalid override depends on widget attrs retained"
  ],
  "design_language_fit": "violates Bootstrap form-validation JS contract; relies on widget.is-invalid class persisting across re-render",
  "user_impact": "search-fail state not retained visually after a server-render roundtrip; users lose visible error context",
  "recommended_fix": "ensure input renders with `.is-invalid` from server template when context.has_search_error is set; do not change validation semantics",
  "regression_risk": "medium",
  "validation": ["768 search-failed after re-render diff", "keyboard trace to retry button"]
}
```

> Note: the fix for UI-005 dances near BugGuard territory because it depends on what the view passes to the template. The view contract (does it set `has_search_error`?) is BugGuard-owned. UI's safe scope is the template-side rendering of `.is-invalid` when that context key is present.

## Triage

- must fix: UI-005
- should fix: UI-002
- defer: replace `.spinner-border` with skeleton loader (separate task)
- do not touch: search validation rules, view contract for `has_search_error` (BugGuard surface)

## Sample opposition findings (Stage 9)

```text
Finding OPP-001
Proposed change: Remove inline style:background:#1f4d8c from table header; use .table-dark for the header row.
Challenge surface: visual consistency
Decision: ACCEPT
Reason: .table-dark is the Bootstrap-native mechanism, reuses Bootstrap's primary theme variable for the dark-row background, matches the dark-mode toggle. No new token.
Evidence cited: design-language.md (must_reuse Bootstrap component classes), scss/_variables.scss:8 ($primary) + Bootstrap .table-dark docs.
```

```text
Finding OPP-002
Proposed change: Render .is-invalid on input when context.has_search_error is set, server-side template fix.
Challenge surface: scope
Decision: ACCEPT WITH MODIFICATION
Reason: The template-side change is in scope. The view-side change that sets has_search_error is BugGuard territory — the template change can land first; flag the view-side contract change for BugGuard follow-up.
Safer alternative: land the template-side class rendering only; do not touch the view function. Document the BugGuard handoff.
Evidence cited: bugguard-boundary.md (UI owns template class rendering; view contract owned by BugGuard), interaction trace evidence/before/768-search-failed-interaction.md.
```

## Synthesised plan (Stage 10)

1. **UI-002** — accept as proposed. File: `templates/admin/users.html:18`. Remove inline `style=`; add `.table-dark` to the header row (`<thead class="table-dark">`). Validation: 1280 light + dark diffs confirm same colour; no regression outside touched header.
2. **UI-005** — modified. File: `templates/admin/_user_row.html` (or equivalent search input partial). Render `.is-invalid` when `has_search_error` context is true. **BugGuard handoff note**: the view function must reliably set `has_search_error`; tracked as follow-up issue UI-005B in the report.
3. Spinner → skeleton: defer.

## Final report excerpt (Stage 15)

> The admin user table's header row now uses Bootstrap's `.table-dark` instead of an inline `style:background:#1f4d8c`, restoring single-source brand colour through `$primary`/`--bs-body-*`. The search-fail visual state is rendered through `.is-invalid` when `has_search_error` is present, preserving Bootstrap form-validation semantics; the view-side contract that sets `has_search_error` is logged for BugGuard follow-up. No new tokens, colours, components, or dependencies introduced; density and dark-theme plumbing preserved.

## What this example is for

Shows the design-system-cleanup mode: small surface-internal fixes that consolidate the design system rather than expand it. Two recurring themes: distinguishing Sass (`$var`) vs CSS custom properties (`--bs-*`) — and using both in their right layer — and the BugGuard boundary at the view/template interface where template class rendering is in scope but view context contract is out of scope.