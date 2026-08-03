---
pack: design-systems.component-anatomy
version: 2026-07
authorities:
  - W3C WAI-ARIA APG
  - web.dev Learn CSS
load_when:
  - component state improvement
  - visual polish
  - design-system cleanup
  - introducing/styling a control
rules:
  - A component has anatomy: parts, states, variants, density options
  - State is mandatory, not optional: default / hover / focus-visible / active / disabled / loading / empty / error / success
  - Variants follow naming convention; a new variant needs the variant pattern, not a one-off
  - Anatomy applies across surfaces: a card is a card is a card
validation_checks:
  - state matrix per touched component
  - variant consistency across surfaces
  - keyboard invariants (focus-visible) preserved
  - loading/empty/error states present where data flows in
false_positives:
  - "missing state" where the surface genuinely does not exhibit it (e.g. no loading state on a static label)
anti-patterns:
  - existent variants duplicated under a new name
  - missing focus-visible because hover covers it
  - disabled states that look like enabled-but-faded and have no a11y signal
report_snippets:
  - "Component state matrix: default/hover/focus-visible/active/disabled/loading/empty/error — all present"
  - "Variants: primary/secondary/ghost reused; no new variant introduced"
---

# Pack: Design systems — component anatomy

Components drift when each surface styles the same control a little differently. Anatomy fixes that: every component below to a list of parts, states, variants, density options, and keyboard invariants.

State matrix reference (see `audit-taxonomy.md` component state mode):

```text
default, hover, focus-visible, active, disabled, loading, empty,
error, success, selected, expanded, collapsed, long content,
short content, permission denied, offline/network error
```

A change that adds a state must reuse the existing component's affordance, not invent a parallel one. A change that introduces a variant must follow the variant pattern; an off-script "card-alt" is drift.