---
pack: anti-unsafe-redesign
version: 2026-07
authorities:
  - (internal; safety pack)
load_when:
  - user asks for global / wide redesign
  - "match screenshot" or "implement design" extends to multiple surfaces
rules:
  - A redesign must scope before implementing; map affected surfaces, not file-by-file rewrites
  - Cross-surface redesigns need a documented "before" language snapshot to compare against
  - Rollback plan required (file list + prior values + prior tokens)
  - Token migration is part of redesign; do not let two systems coexist silently
  - Custom widget redesign re-runs APG keyboard model
validation_checks:
  - surface sampling covers representative surfaces
  - "before" language snapshot in design-language.md
  - affected token system identified
  - rollback plan exists
anti-patterns:
  - ad-hoc redesign that leaves half the product in old language
report_snippets:
  - "Redesign scope: N surfaces; before-snapshot in design-language.md; token migration plan accepted; rollback plan in reports/ui-change-plan.md"
---

# Pack: Unsafe redesign

Wide redesigns are the highest-regret UI changes. They look like polish but they replace a design system. The skill should:

- scope affected surfaces before any edit
- snapshot the "before" language in `design-language.md`
- identify the token migration (old tokens -> new tokens; removal of orphans)
- require a rollback plan in the change plan
- re-run APG keyboard modeling on any custom widget

The `implement design` and `full surface refinement` modes load this pack by default.