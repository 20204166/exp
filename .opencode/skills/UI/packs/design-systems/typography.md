---
pack: design-systems.typography
version: 2026-07
authorities:
  - web.dev Learn CSS: typography
  - MDN font-display
  - W3C Accessibility: text spacing
load_when:
  - visual polish
  - design-system cleanup
  - typography debt observed
rules:
  - One type scale; one source of truth (token / theme / config)
  - Line-height paired per usage (tight for headings, relaxed for body)
  - font-display set on web fonts to avoid FOIT; size swap to avoid major layout shift
  - WCAG 1.4.4: text resizable to 200% without loss; 1.4.10: reflow at 320 CSS px
  - Do not introduce a new font family to fix one screen
  - Body line-height around 1.5; large text around 1.2 as starting point, project may differ
validation_checks:
  - scale tokens (font-size + line-height pairs)
  - font-display declared
  - no new hardcoded font sizes duplicating tokens
  - reflow at 320 CSS px: no horizontal scroll on text surfaces
false_positives:
  - "tight line-height" on a single decorative heading — may be intentional
anti-patterns:
  - magic px font sizes
  - introducing a display font for one card
  - body text at less than 16px on web (review; some admin density may use 14px with sufficient contrast)
report_snippets:
  - "Type scale: 5 tokens used; no new font sizes introduced"
framework_notes:
  - Tailwind: font-size + line-height paired in theme.fontSize
---

# Pack: Design systems — typography

Type has rhythm. The product carries a scale; respect it instead of minting px values.

Inference dimensions: family (sans/serif/mono), scale (heading + body), weight usage, line-height pairs, font-display policy, density (size relative to admin baseline).

A common debt pattern: a single hero or card using a one-off px font-size. The fix is to use the closest existing token — not to introduce a new token for one occurrence.

Reserve web-font usage for actual brand/type intent; arbitrary weight adds loading cost and CLS.