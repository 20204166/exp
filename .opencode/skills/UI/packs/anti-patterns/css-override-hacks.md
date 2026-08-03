---
pack: anti-patterns.css-override-hacks
version: 2026-07
authorities:
  - MDN Cascade / specificity / layers
load_when:
  - css architecture audit
  - implementation where an override is the proposed fix
rules:
  - Override hacks: `!important`, ID selectors, descendant stacking, `:where(:not(.x))` for specificity games, layer ordering to win one fight
  - Prefer: token change, variant reuse, component-local style, scoped selector, then layer (intentional), then import (last resort)
validation_checks:
  - net `!important` count not increased
  - no ID selector added without explicit reason
  - no descendant chains (>3 deep) added
  - no cross-surface leak from a local override
false_positives:
  - intentional `:where()` to lower specificity is the inverse of an override hack and is fine
report_snippets:
  - "Override check: 0 new !important, 0 new ID selectors, 0 descendant chains >3"
---

# Pack: CSS override hacks

Override hacks are how UI changes win specificity fights without understanding the cascade. Each hack kicks debt forward and makes the next change harder.

The pack flags: new `!important`, new ID selectors, descendant stacking (`.a .b .c .d`), layer ordering to win a local fight, `:where(:not(.x))` games, specificity-targeting utility classes.

Acceptable uses are rare and require explicit justification in the change plan. The preferred order falls out of `implementation-rules.md` CSS change hierarchy: token -> variant -> component-local -> utility -> global -> layer -> dependency. Hacks come after all of those are exhausted.