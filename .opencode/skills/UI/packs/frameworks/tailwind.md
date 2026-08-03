---
pack: frameworks.tailwind
version: 2026-07
authorities:
  - Tailwind CSS docs
load_when:
  - tailwind detection
rules:
  - Tailwind is utility-first and breakpoint-driven; architecture differs from Bootstrap (component-first)
  - Tokens live in `tailwind.config.*` (theme); files reference them through utilities
  - Responsive variants (`sm:` / `md:` / `lg:`) come from theme; arbitrary breakpoints (`min-[723px]:`) are drift
  - Arbitrary values (`p-[14px]`) are appropriate for genuine one-offs, drift when used repeatedly
  - Container queries via `@container` and `@sm:` / `@md:` variants
validation_checks:
  - arbitrary value use inventoried; 3+ occurrences -> token candidate
  - breakpoint variants only (no raw `@media` mixed in disagreement)
  - theme extending includes new tokens rather than raw values
  - `@layer base/components/utilities` order intentional, not patchwork
false_positives:
  - "use a token" on a genuine one-off arbitrary value (single occurrence)
anti-patterns:
  - hardcoding `@media (min-width: 723px)` separately from tailwind breakpoints
  - `!p-4` (important) to win a single override
  - arbitrary `p-[14px]` repeated across surfaces instead of `p-3.5` or a token
report_snippets:
  - "Tailwind: theme tokens reused; N arbitrary-value occurrences; 0 new breakpoints"
---

# Pack: Tailwind

Tailwind is utility-first and breakpoint-driven. Its architecture is opposite to Bootstrap (component-first), so treat it as such rather than "just CSS".

Discovery and audit focus on:

- theme tokens (`theme.colors`, `theme.spacing`, `theme.fontSize`, `theme.radius`, ...)
- utility usage consistency
- responsive variants from theme breakpoints
- arbitrary-value usage drift (`p-[14px]` appearing many times is a token candidate)
- `@layer` order if the project uses layers
- container-query variants (`@container`, `@sm`)

Do not introduce raw `@media` queries that disagree with theme breakpoints. Do not `!p-4` to win one override — escalate via the cascade rather than important-escaping one utility.