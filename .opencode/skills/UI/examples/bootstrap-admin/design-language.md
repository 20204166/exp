# Design language (condensed example) — Admin user table

Surface slug: `admin-users`. Stack: Bootstrap 5.2 (Sass + custom properties).

## Inferred

- **Brand tone:** enterprise admin — utility, table-dense, no marketing voice.
- **Density:** compact — row padding tighter than default Bootstrap (`$table-cell-padding-y` reduced).
- **Spacing rhythm:** Bootstrap `$spacer` scale with project overrides; row gaps `$spacer * .5`.
- **Type scale:** Bootstrap `$font-size-base` 14px overridden to 13px in admin context; weights 400/600.
- **Colour:** `$primary` (override at `#1f4d8c` for brand); `$gray-700` for body text; semantic via Bootstrap `text-success`/`text-danger`/`text-warning`. Dark theme via `data-bs-theme="dark"` overrides body tokens via `--bs-body-*`.
- **Radius:** reduced Bootstrap defaults — `$border-radius` 4px (override); table corners sharp.
- **Shadow / elevation:** minimal — only `.card` gets `shadow-sm`. No elevation on table.
- **Icon style:** Bootstrap Icons (outline) at 14px.
- **Component conventions:** table uses Bootstrap `table` + `table-hover`; row actions in a `dropdown-menu`; filter chips use `.btn-group`.
- **Button hierarchy:** `.btn-primary` (filled brand) for bulk action; `.btn-outline-secondary` for per-row; `.dropdown-item` for menu actions.
- **Form style:** `.form-control` reused throughout; inline search; `.is-invalid` flashes on failed search submit.
- **Empty / loading / error states:** Bootstrap `.text-center py-5` empty state with copy + CTA; loading uses Bootstrap `.spinner-border`; error path uses `.alert alert-danger`.
- **Layout grid:** `container-fluid` admin shell; sidebar 240px on `lg`; stacked below `lg`.
- **Animation personality:** none — Bootstrap defaults only; tooltip pop uses Bootstrap JS timing.

## Constraints

### must_reuse
- `$primary` (override), `$gray-*`, `$border-color` Sass overrides
- `--bs-body-*` CSS custom properties for theme (they toggle with `data-bs-theme`)
- Bootstrap component classes `table`, `btn-*`, `dropdown-*`, `form-control`, `alert`, `spinner-border`
- Bootstrap state classes `.active`/`.disabled`/`.show`/`.is-invalid`

### must_preserve
- compact admin density on table rows
- Bootstrap JS dependence on `data-bs-*` hooks (`data-bs-toggle`, `data-bs-target`, `data-bs-dismiss`)
- `data-bs-theme="dark"` runtime theming (do not duplicate dark styles inline)
- `.is-invalid` semantics wired to Bootstrap form validation JS

### do_not_introduce
- Hand-rolled table components replacing `.table`
- Inline `style=` overrides to fix per-row density
- New dark-mode CSS that duplicates `--bs-body-*` plumbing
- New primary colour outside `$primary` override

### spa_or_marketing_only
- 28px+ row padding
- New accent gradient

## Tokens (summary)

Sass vars + runtime CSS custom properties coexist. Single-source candidates:

| Name | Layer | Value | Source | Duplicate of |
|---|---|---|---|---|
| `$primary` | Sass | #1f4d8c | `scss/_variables.scss:8` | - |
| `$table-cell-padding-y` | Sass | .25rem | `scss/_variables.scss:42` | - |
| `--bs-body-color` | CSS | - | Bootstrap set by `data-bs-theme` | - |
| `#1f4d8c` | hardcoded hex | - | `templates/admin/users.html:18` (table header) | `$primary` — DUPLICATE |

Hardcoded `#1f4d8c` appears in the table header template — that's design-system cleanup number one. Same value as `$primary`, declared as raw hex.

## Evidence

| id | kind | ref | claim |
|---|---|---|---|
| E1 | screenshot | `evidence/before/1280-light.png` | compact density, dark-column header |
| E2 | css | `scss/_variables.scss:8` | `$primary` = #1f4d8c |
| E3 | css | `templates/admin/users.html:18` | hardcoded `#1f4d8c` in table header style attr |
| E4 | css | `scss/_variables.scss:42` | `$table-cell-padding-y` override reduced |
| E5 | a11y-tree | dropdown button has `aria-expanded` toggling | Bootstrap JS keyboard model intact |

## Governing rule

> Polish the existing product, not redesign it.