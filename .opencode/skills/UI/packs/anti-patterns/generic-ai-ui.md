---
pack: anti-generic-ai-ui
version: 2026-07
authorities:
  - (internal) product preservation pack
  - W3C prefers-reduced-motion (for motion-related sub-rules)
load_when:
  - any visual polish task
  - implement design (loaded with caution; explicit request widens do_not_introduce)
  - match screenshot
  - default-loaded during design-language inference
blocks:
  - random gradients
  - unrequested glassmorphism
  - new colour palettes
  - new shadows everywhere
  - generic SaaS cards
  - inconsistent rounded corners
  - overuse of emoji / icons
  - fake "premium" polish
  - unnecessary animations
  - marketing-style redesign of utility / admin screens
  - invented empty states that change product tone
enforces:
  - reuse existing tokens
  - reuse existing component language
  - improve hierarchy before decoration
  - improve spacing before adding effects
  - prefer restraint
  - preserve product personality
validation_checks:
  - proposed change cites a reused token or existing variant
  - no new gradient / shadow / glass effect unless explicitly requested
  - no new accent colour outside the colour token family
  - no marketing-style spacing on admin / utility surfaces
  - empty-state style consistent with the product's existing empty states
false_positives:
  - "gradient introduced" where the product already uses gradients intentionally — check design-language.md
report_snippets:
  - "Anti-generic-AI: change reuses --space-4 and the existing card variant; no new gradients, shadows, or effects introduced"
---

# Pack: Anti-generic AI UI

This is the single most important anti-pattern this skill defends against. Without design-language inference plus this pack, an implementation drifts toward generic AI UI debt:

- random gradients
- new shadows everywhere
- glassmorphism nobody asked for
- new accent colours
- generic SaaS "clean dashboard" cards
- inconsistent rounded corners
- fake premium polish
- decoration on a utility / admin product
- invented empty states that change product tone

Default behaviour of the skill: **polish the existing product, not redesign it.**

The rule this pack enforces:

```text
Do not introduce a new visual language unless explicitly requested.
```

"Explicitly requested" means the user named the affected language explicitly ("introduce dark mode", "redesign the empty state", "switch to rounded cards"). A vague "make it look better" is a request to polish within the existing language; it is not a request to redecorate.

The pack loads by default during design-language inference. For `implement design` mode it still loads; the design-language `do_not_introduce` constraints may be widened only with an explicit user request, and the widening is recorded in the change plan. Hand-widening is a non-negotiable violation.

For every accepted change the report must answer one sentence: what existing token or variant did this change reuse? If the answer is "none — it introduced a new one", the report must also state why the introduction was the smallest feasible option, with opposition's acceptance on record.