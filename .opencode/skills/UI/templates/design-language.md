# Design Language — {surface}

Mandatory artifact (Stage 3). Conforms to `schemas/design-language.schema.json` (machine-readable companion: `design-language.json`).

This file is the main defence against generic AI UI. Before proposing any visual change, infer and record the existing product language here.

---

## Surface

- Slug: {slug}
- Stack: {react / vue / jinja / django / flask / fastapi / tailwind / bootstrap / vanilla css / scss / css modules / css-in-js / unknown}
- Evidence sources: {templates, css files, screenshots, accessibility tree signals}

## Inferred dimensions

> Every row must cite at least one evidence row in the "Evidence" section below.

### Brand tone
{composition, e.g. "utility / admin / enterprise — restrained, table-dense, no marketing voice"}

### Density
{compact / cozy / comfortable / airy}

### Spacing rhythm
{base unit, scale, evidence}
- Example: "8px base; scale 2/4/8/12/16/24/32; verified on `static/css/app.css:--space-*`"

### Type scale
{font sizes + line-heights + families}

### Colour usage
{semantic / neutrals / accent}

### Border radius language
{sharp / soft / pill / mixed}

### Shadow / elevation style
{flat / light / layered / none}

### Icon style
{outline / solid / duotone / illustrated / none}

### Component conventions
{card chrome, table density, form control style, ...}

### Button hierarchy
{primary / secondary / tertiary / ghost variants}

### Form style
{label position, error placement, control density}

### Empty / loading / error state style
{skeleton / spinner / illustration / copy}

### Layout grid
{columns, gutters, container widths, breakpoints}

### Animation personality
{none / functional transitions / motion-heavy / playful}

## Constraints

(These gate change proposals. See `packs/anti-patterns/generic-ai-ui.md`.)

### must_reuse
- {token / variant / pattern}

### must_preserve
- {product-language trait}

### do_not_introduce
- random gradients
- unrequested glassmorphism
- new colour palettes
- new shadows everywhere
- generic SaaS cards
- inconsistent rounded corners
- overuse of emoji / icons
- fake "premium" polish
- unnecessary animations
- marketing-style redesign of utility / admin screens
- invented empty states that change product tone

(Widen `do_not_introduce` only with an explicit user request.)

### spa_or_marketing_only
- {patterns allowed only on (S)PA/marketing surfaces, e.g. 28px padding, large hero shadows}

## Tokens (inventory summary)

| Name | Value | Source | Duplicate of |
|---|---|---|---|
| `--space-4` | `1rem` | `static/css/app.css:42` | - |
| `--color-text-primary` | `#1a1a1a` | `static/css/app.css:7` | - |
| ... | | | |

(Duplicate-value candidates and single-use tokens flagged here. Full inventory in optional `token-inventory.json`.)

## Evidence

| id | kind | ref | claim |
|---|---|---|---|
| E1 | screenshot | evidence/before/dashboard-default-1280.png | density: compact |
| E2 | css | static/css/app.css:42 | spacing token --space-4 = 1rem |
| E3 | dom | fieldset > legend + label | form-style: legend per group, label per field |

## Governing rule

> Do not introduce a new visual language unless explicitly requested.

"Explicitly requested" means the user named the affected part of the language. "Make it look better" is polish, not redesign.