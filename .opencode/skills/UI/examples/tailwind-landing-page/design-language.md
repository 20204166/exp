# Design language (condensed example) — Landing page

Surface slug: `landing`. Stack: Tailwind v4 (`@import "tailwindcss"`, `@theme` overrides).

## Inferred

- **Brand tone:** marketing — wider rhythm, larger hero, motion-light.
- **Density:** comfortable — hero padding 64px desktop / 32px mobile; feature grid gap 24px.
- **Spacing rhythm:** Tailwind 4px base scale (`theme.spacing`), screens at theme breakpoints (default sm/md/lg/xl/2xl). Some arbitrary-value drift (see tokens note).
- **Type scale:** Tailwind `theme.fontSize` reused; hero H1 uses `text-5xl` on `lg` and `text-4xl` on `md` per responsive variants.
- **Colour:** neutrals from `theme.colors.neutral`; accent `--color-accent` for primary CTA; semantic for status but landing surface has few of those.
- **Radius:** `theme.radius` defaults; CTA `rounded-full` (pill); cards `rounded-2xl`.
- **Shadow / elevation:** marketing — `shadow-xl` reserved for hero card; feature tiles have none.
- **Icon style:** outline icons 24px.
- **Component conventions:** hero uses full-width responsive container; feature grid uses `@container` so each card reflows based on container not viewport.
- **Button hierarchy:** primary `btn-primary` (filled accent, rounded-full), secondary (text-link style).
- **Form style:** none on landing; the email capture is a single inline field in CTA.
- **Empty / loading / error states:** hero image loading rendered as a `bg-gradient-to-r` placeholder; image-fail path currently has no alt block (deferred — BugGuard surface).
- **Layout grid:** max-width 1200px container; feature grid `grid-cols-1 md:grid-cols-3`.
- **Animation personality:** marketing-light — fade-in on hero via opacity transition 600ms; honours `prefers-reduced-motion`.

## Constraints

### must_reuse
- Tailwind theme tokens (`theme.colors`, `theme.fontSize`, `theme.radius`, `theme.spacing`)
- existing responsive variants from `theme.screens` (no raw media queries)
- existing `@container` utilities for feature grid card behaviour
- `prefers-reduced-motion` collapse

### must_preserve
- comfortable marketing density
- CTA pill (`rounded-full`) on primary; do not switch to soft radius without explicit ask
- container-query-driven feature cards
- hero image loading gradient placeholder

### do_not_introduce
- Arbitrary breakpoints outside `theme.screens`
- New palette colours outside `theme.colors`
- Heavy parallax / scroll-jacking motion
- New fonts / display font not in `theme.fontFamily`

### spa_or_marketing_only
- `shadow-xl` (already used on hero card only)
- 28-32px hero padding (already used on hero only)

## Tokens (summary)

Tailwind theme tokens. Arbitrary-value hotspots:

| Class | Count | Notes |
|---|---|---|
| `p-[14px]` | 4 | duplicate of `theme.spacing` step? consider token |
| `gap-[18px]` | 3 | candidate for `gap-4.5` token extension |
| `min-[723px]:hidden` | 0 (none) | none introduced (good) |

## Evidence

| id | kind | ref | claim |
|---|---|---|---|
| E1 | screenshot | `evidence/before/375-default.png` | comfortable density at mobile |
| E2 | css | `tailwind.config.ts:12-34` | theme.screen tokens |
| E3 | css | `src/styles/globals.css:8-22` | `@theme` overrides |
| E4 | dom | feature grid cards have `@container` ancestor | container-query-driven |

## Governing rule

> Polish the existing product, not redesign it.