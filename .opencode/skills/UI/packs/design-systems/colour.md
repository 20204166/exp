---
pack: design-systems.colour
version: 2026-07
authorities:
  - W3C WCAG 1.4.3 / 1.4.11 contrast
  - MDN color
load_when:
  - visual polish
  - design-system cleanup
  - theming / dark mode
  - contrast issue
rules:
  - One colour source-of-truth (tokens / theme / config)
  - Semantic colours (success/warn/error/info) separate from neutrals + accent
  - WCAG 1.4.3: text 4.5:1 (large 3:1); 1.4.11: non-text 3:1
  - Dark mode is a separate theme, not a CSS light-mode hack
  - Do not introduce a new colour to fix one screen
  - Focus indicators need 3:1 against adjacent colours and remain visible (2.4.7, 2.4.11)
validation_checks:
  - grep for hardcoded hex/rgb/hsl appearing 3+ times
  - contrast pass on touched text + non-text
  - dark mode theme uses its tokens, not "light + opacity hacks"
  - focus indicator contrast passes at every state touched
false_positives:
  - "low contrast" on decorative-only elements (no text or meaning)
  - "use a token" when the value is genuinely novel — review (single-use vs token candidate)
anti-patterns:
  - hardcoded #fff / #000 / #ddd instead of tokens
  - "backdrop-filter with implicit dark text on unknown backgrounds" — contrast unverified
  - new accent colour introduced for one card
report_snippets:
  - "Colour: N tokens reused; 0 new hardcoded colours; dark theme tokens used"
framework_notes:
  - Tailwind: `theme.colors` + opacity variants
  - Bootstrap: theme variables (CSS custom properties) + Sass overrides; do not mix raw Sass var with CSS custom property for the same role
---

# Pack: Design systems — colour

Colour debt shows as duplicate hex values, hardcoded `#fff`, multiple "almost the same grey" tokens, and ad-hoc accent colours. Like spacing, the drift is small per occurrence and visible in aggregate.

The pack applies contrast checks (text and non-text) and asks whether the colour comes from a token source. A colour appears 3+ times → tokenize. A colour appears once → use an existing token if one fits.

Dark mode is its own theme with its own tokens. A "light + dark via opacity" hack tends to underdeliver contrast in one direction; token both directions explicitly.