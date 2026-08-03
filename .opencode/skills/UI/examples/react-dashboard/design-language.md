# Design language (condensed example) — Operations dashboard

Surface slug: `ops-dashboard`. Stack: React + CSS Modules.

## Inferred

- **Brand tone:** enterprise ops console — utility, table-dense, no marketing voice.
- **Density:** compact-cozy — tile padding 24px, internal gaps 12px.
- **Spacing rhythm:** 4px-base scale, `--space-2`/`--space-4`/`--space-6` (0.5/1/1.5rem). Evidence `src/styles/tokens.module.css`.
- **Type scale:** 12px meta / 14px body / 16px tile title / 28px metric figure. Line-height 1.4 body, 1.1 figure.
- **Colour:** neutrals + semantic `--color-success/-warn/-danger/-info`. Single accent `--color-accent` used for active state.
- **Radius:** `--radius-md` (8px) on tiles/cards/charts; sharp corners only on tables.
- **Shadow / elevation:** `--shadow-1` for elevated tiles, flat for table rows. No glossy shadows.
- **Icon style:** outline icons in 16/20 sizes; no illustrative icons on dashboards.
- **Component conventions:** tile chrome = 24px padding, elevation shadow, no internal border; hover raises shadow briefly.
- **Button hierarchy:** primary filled `--color-accent`; secondary outlined; tertiary text-link.
- **Form style:** compacter than the surface-form case — filter chips; inline search.
- **Empty / loading / error states:** skeleton (shimmer) on loading; copy + retry CTA on error; copy + CTA on empty.
- **Layout grid:** desktop sidebar 240px + main; 1024 -> stacked single-column.
- **Animation personality:** functional — transitions on hover/elevation only; 200ms `--motion-fast` on composited properties.

## Constraints

### must_reuse
- `--space-2/-4/-6`, `--color-*` semantics, `--radius-md`, `--shadow-1`, `--motion-fast`
- existing Tile/Card component variants
- existing skeleton rendering component

### must_preserve
- compact-cozy density
- composited-only transitions
- skeleton loading pattern (not a new spinner)
- accent-colour usage (single accent reserved for active state)

### do_not_introduce
- New glassmorphism / backdrop-filter dashboards
- New accent colours per metric
- New shadow flavours (use `--shadow-1`)
- Custom keyframe entrance animations on tiles
- Decorative 3D / bevel effects on figures

### spa_or_marketing_only
- Heavy hero shadows (> `--shadow-1`)
- Animated chart entrance with bouncy easing

## Tokens (summary)

| Name | Value | Source | Duplicate of |
|---|---|---|---|
| `--space-2` | 0.5rem | `src/styles/tokens.module.css:5` | - |
| `--space-6` | 1.5rem | `src/styles/tokens.module.css:7` | - |
| `--color-accent` | #2563eb | `src/styles/tokens.module.css:14` | - |
| `--shadow-1` | 0 1px 3px rgba(0,0,0,0.12) | `src/styles/tokens.module.css:22` | - |
| `--motion-fast` | 200ms | `src/styles/tokens.module.css:28` | - |

## Evidence

| id | kind | ref | claim |
|---|---|---|---|
| E1 | screenshot | `evidence/before/1280-default.png` | compact-cozy density |
| E2 | css | `src/styles/tokens.module.css:22` | elevation token `--shadow-1` |
| E3 | dom | `<section role="main">` contains tiles | landmarks present |
| E4 | a11y-tree | tiles have heading + figure | heading order clean |

## Governing rule

> Polish the existing product, not redesign it.