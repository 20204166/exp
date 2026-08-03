# Adapter — Tailwind

How Stage 1/11/12-14 differ for Tailwind. Use with `packs/frameworks/tailwind.md`.

## Surface discovery (Stage 1)

- Detect Tailwind major version (v3 vs v4 differ materially in CSS architecture: v4 uses `@import "tailwindcss"` and native CSS layering; v3 uses PostCSS + JS config).
- Map `tailwind.config.*` keys: `theme.extend`, `theme.colors`, `theme.spacing`, `theme.fontSize`, `theme.radius`, `theme.screens`.
- Map custom plugins (`typography`, `forms`, `aspect-ratio`, `container-queries`).
- Map content globs — files outside globs do not get utilities purged in v3 / scanned in v4.
- Detect `@layer base/components/utilities` usage in source CSS.
- Detect arbitrary-value classes in the touched templates/components; record their density (3+ same-value arbitrary classes = token candidate).

## Edits (Stage 11)

- Prefer an existing utility or theme token over an arbitrary value.
- Prefer extending `theme.extend` over `theme` overrides (extend does not unset existing tokens).
- Responsive variants come from `theme.screens`; do not introduce `@media (min-width: 723px)` lanes outside the config.
- Container queries in v3 require the `container-queries` plugin and `@container`/`@sm:` / `@md:` variants; v4 supports them natively. Use container-query variants for components in narrow containers, not raw media queries.
- Tailwind v4: customisation may live in CSS via `@theme`; do not hand-edit `tailwind.config.js` for v4 setups unless that's the project's chosen source of truth.
- Use `!important` modifier (`!p-4`) sparingly; escalate via the cascade, not via important-escape one utility.

## Validation (Stages 12-14)

- Build output CSS post-purge/post-scan to confirm the utilities you expect actually exist; Tailwind utility class names not in `content` globs are dropped.
- Inspect compiled CSS for actual utility order — `@layer` order decides utility precedence in v3.
- For responsive fixes, capture per-viewport rendered DOM; do not infer from the class list alone.