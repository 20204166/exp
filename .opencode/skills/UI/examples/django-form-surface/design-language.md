# Design language (condensed example) — Refund claim form

Surface slug: `claims-new`. Stack: Django + crispy-forms.

## Inferred

- **Brand tone:** utility / enterprise refund portal — restrained, no marketing voice on form surfaces.
- **Density:** compact — admin density; row gaps tight.
- **Spacing rhythm:** 4px-base scale, `--space-2` (.5rem) within field groups, `--space-4` (1rem) between groups. Evidence `static/css/forms.css:18-29`.
- **Type scale:** 14px body / 16px field labels / 20px H1. Line-height 1.5 for body, 1.25 for labels. Evidence `static/css/app.css:5-12`.
- **Colour:** neutrals `--color-text-primary`/`--color-text-muted`; semantic `--color-danger` (`#b91c1c`) for errors, `--color-success` (`#15803d`) for submit success. Evidence `static/css/app.css:7-9` + `:24`.
- **Radius:** `--radius-md` (6px) on inputs/buttons; sharp corners on table-style layout only.
- **Shadow / elevation:** flat — no shadows except modal/dialog.
- **Icon style:** outline icons from the project's icon font, 16px.
- **Component conventions:** form groups stack vertically; labels above inputs; error block appears below the input, not next to it; stepper renders horizontally on >=768.
- **Button hierarchy:** primary `btn-primary` (filled), secondary `btn-secondary` (outlined), text link for "Cancel".
- **Form style:** label-top; `is-invalid` / `is-valid` state classes (Bootstrap-compatible via crispy forms); error text in `--color-danger`.
- **Empty / loading / error states:** inline error per field; top-level alert at the top of the form on submit-failure; spinner in submit button on submit-loading.
- **Layout grid:** max-width 720px centered on desktop; full-width on mobile; container queries NOT in use (this is admin utility, viewport-responsive suffices here).
- **Animation personality:** minimal — spinner on submit; no entry animation.

## Constraints

### must_reuse
- `--space-2`, `--space-4` (no arbitrary padding)
- `--color-danger`, `--color-success` (no hardcoded hex for errors/success)
- `--radius-md` on form controls
- existing `btn-primary` / `btn-secondary` variants

### must_preserve
- compact admin density
- 4px-base spacing rhythm
- label-top form convention
- inline + top-level error display both kept (not one or the other)
- formatting of CSRF token block

### do_not_introduce
- New gradients / glassmorphism / hero shadows
- New accent colours
- Marketing-style spacing
- Marketing empty-state illustrations

### spa_or_marketing_only
- 28px+ padding (only marketing pages)

## Tokens (summary)

| Name | Value | Source | Duplicate of |
|---|---|---|---|
| `--space-2` | 0.5rem | `static/css/app.css:18` | - |
| `--space-4` | 1rem | `static/css/app.css:19` | - |
| `--color-text-primary` | #1a1a1a | `static/css/app.css:7` | - |
| `--color-danger` | #b91c1c | `static/css/app.css:24` | - |
| `--radius-md` | 6px | `static/css/app.css:35` | - |

## Evidence

| id | kind | ref | claim |
|---|---|---|---|
| E1 | screenshot | `evidence/before/375-default.png` | density is compact at 375 |
| E2 | css | `static/css/forms.css:18-29` | `--space-2` within, `--space-4` between |
| E3 | dom | form > fieldset > legend + label per field | form-style: legend per group, label-top per field |
| E4 | css | `static/css/app.css:24` | `--color-danger` semantic for errors |

## Governing rule

> Polish the existing product, not redesign it.