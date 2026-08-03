---
pack: css.cascade-layers
version: 2026-07
authorities:
  - MDN @layer
  - W3C CSS Cascading and Inheritance
load_when:
  - css architecture audit
  - design-system cleanup
  - introducing new global styles
  - specificity escalation observed
rules:
  - Cascade layers define precedence between groups of styles, not inside them
  - Introducing @layer to an existing codebase is a migration, not a one-off override
  - Layer order should be declared once, at the root stylesheet
  - Tailwind/Bootstrap already have layering semantics; check before adding your own
  - Do not use @layer as a substitute for tokenizing
validation_checks:
  - layer order declaration present and intentional
  - specificity inside layers did not escalate
  - no cross-layer overrides rely on magic order
false_positives:
  - "@layer needed for override" when a token or component-local style would suffice
anti-patterns:
  - ad-hoc @layer added to win a single specificity fight
  - wrapping everything in @layer to "modernize" without a migration plan
report_snippets:
  - "Layers declared: reset, base, components, utilities; precedence order recorded"
framework_notes:
  - Use cascade layers when precedence across groups is the actual problem (framework vs project overrides)
  - Do not introduce cascade layers to fix one override; use a more specific scoped selector or a token
---

# Pack: CSS cascade layers

Cascade layers are one possible modernization path for managing precedence between groups of styles. They are not a default rewrite tool: introducing them into an old codebase is itself a migration risk and should be planned, not ad-hoc.

Precedence inside a layer is normal CSS specificity. Layers set precedence *between groups* (e.g. base < components < utilities). Misusing @layer to win a single specificity fight destabilises the cascade and makes future overrides harder to reason about.

Use layers when:

- a framework and project overrides compete for precedence
- a design system wants to declare primary intent vs override intent
- a migration has a documented phase plan

Do not use layers when:

- a single class override will do
- a token change will do
- a more specific scoped selector will do