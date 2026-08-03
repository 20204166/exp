---
pack: frameworks.scss
version: 2026-07
authorities:
  - Sass documentation
  - MDN CSS preprocessors
load_when:
  - scss detection
  - css architecture audit
rules:
  - Sass variables (`$var`) are compile-time; CSS custom properties (`--var`) are runtime
  - `@use` / `@forward` are the modern module system; `@import` is the legacy form
  - Partials (`_*.scss`) compose the build; one tokens partial should be the single source
  - Mixins can hide repeated magic values; prefer a real token over a mixin for design-language values
  - Selectors in Sass compile to ordinary CSS; specificity rules apply to the compiled output
validation_checks:
  - `@use` over `@import` (modern modules)
  - one shared tokens partial (`_tokens.scss` or equivalent)
  - duplicate $variable values across partials (token candidate)
  - mixins used for structural/semantic repetition, not as token substitutes
false_positives:
  - "duplicate color across partials" may be intentional (e.g. two theme contexts) — review
anti-patterns:
  - `@import` to win ordering fights
  - mixins that scatter the same value rather than referencing a token
  - nested selector chains deeper than 3 levels (compiles to expensive selectors)
report_snippets:
  - "Sass: @use modules, single _tokens.scss, 0 cross-partial duplicate variables"
framework_notes:
  - Bootstrap/Sass: customisation usually runs through `_variables.scss` overrides
  -_audit specificity on compiled CSS, not on partials as written
---

# Pack: SCSS

SCSS adds compile-time variables, partials, mixins, and nesting to CSS. The architectural surface is the partial graph and the tokens partial; the runtime surface is whatever compiles out.

Discovery maps the partials, the entry build files, the tokens partial, the use/import graph, and the mixin catalogue.

Prefer `@use`/`@forward` modules over `@import`. Prefer real tokens over mixins for design-language values (the mixin is a code-organisation tool, not a token mechanism). Specificity audits operate on compiled CSS — a beautifully organised partial can still emit an `!important` war.