---
pack: css.custom-properties-tokens
version: 2026-07
authorities:
  - W3C CSS Custom Properties
  - MDN CSS variables
load_when:
  - css architecture audit
  - design-system cleanup
  - any change that introduces a new colour or spacing value
rules:
  - Tokens are the single source of truth for repeated values (colour, spacing, radius, shadow, z-index)
  - Add a new token only when a repeated pattern exists (3+ call sites); otherwise use an existing one
  - Do not hardcode a colour/spacing that already exists as a token
  - Do not invent a token name that does not match the existing naming pattern
  - Token values live in one place (root / config / theme file), not scattered
validation_checks:
  - grep for hex/rgb/hsl appearing 3+ times — token candidate
  - grep for duplicate spacing (e.g. `padding: 14px` in 4 files) — token candidate
  - new token name matches existing pattern (--space-N, --color-*, --radius-*)
  - no duplicate tokens with the same value under different names
false_positives:
  - "duplicate hex" that is genuinely two unrelated contexts sharing a value
anti-patterns:
  - adding `--brand-blue-500` when `--color-primary` exists
  - shadow tokens that never get reused (single-use tokens)
  - tokens that re-export identical values without a design reason
report_snippets:
  - "Token inventory: N custom properties, M duplicate-value candidates, K hardcoded magic values"
framework_notes:
  - Tailwind: tokens live in `tailwind.config.*` `theme`
  - Bootstrap: tokens in `_variables.scss` and `:root` CSS custom properties
  - SCSS: `$var` is compile-time; runtime custom properties are CSS custom properties
---

# Pack: Custom properties / design tokens

CSS custom properties (and their framework equivalents) are the mechanism that lets UI changes preserve consistency. Without them, changes scatter hardcoded values across files.

Tokenize when:

- 3+ call sites share a value
- the value is design-language meaningful (spacing, colour, radius, shadow, z-index)

Do not tokenize:

- one-off component-local values
- values that are not design-language meaningful (e.g. a single 2px hairline)

Naming must match the existing pattern. A new token whose name does not match is drift.

A token that re-exports an identical value under a new name is noise unless the rename is part of the design system's documented intent.