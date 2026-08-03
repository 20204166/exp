---
pack: design-systems.spacing
version: 2026-07
authorities:
  - web.dev Spacing
  - W3C WCAG 2.5.5/2.5.8 target size
load_when:
  - visual polish
  - design-system cleanup
  - spacing debt observed
rules:
  - One spacing scale; one source of truth (token / theme / config)
  - Use scale units; do not hardcode arbitrary px
  - Internal spacing within a component may be smaller than gaps between components
  - Target size for interactive controls: >= 24x24 CSS px (WCAG 2.5.8), 44x44 ideal (2.5.5 AAA)
  - Container vs viewport: gaps inside cards depend on card width, not viewport
validation_checks:
  - spacing tokens used consistently across touched files
  - no new arbitrary px padding duplicating tokens
  - interactive controls clear the target-size floor
false_positives:
  - "tight spacing" on a dense admin table — may be intentional density; check design-language.md
anti-patterns:
  - "one more px" padding drift across surfaces
  - doubling padding to "feel spacious" against compact-density product
report_snippets:
  - "Spacing: 4px-base scale reused; no new arbitrary values"
---

# Pack: Design systems — spacing

Spacing debt is the loudest UI inconsistency: a card with 14px padding when the system uses 12px, a row gap of 10px when the system uses 8px. The drift is small per occurrence and visible in aggregate.

Inference: base unit (commonly 4px or 8px), scale steps, density setting, container-vs-viewport distinction. Capture these in `design-language.md` before proposing any spacing change.

The fix at scale of 4 vs 8 might look like "make this 12px" but the safe move is to use the closest scale token. The "one more px" drift compounds into visual chaos over time.