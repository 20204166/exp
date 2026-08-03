# Adapter — SCSS

How Stage 1/11/12-14 differ for SCSS. Use with `packs/frameworks/scss.md` and `packs/css/*`.

## Surface discovery (Stage 1)

- Detect Sass version: modern module system (`@use`/`@forward`) vs legacy `@import`.
- Map partial graph: every `_*.scss` and how `app.scss` (or equivalent entry) wires them.
- Map variables (`$var`), mixins (`@mixin`), functions (`@function`), placeholders (`%foo` and `@extend`).
- Identify the token partial that should be the single source of truth; flag duplicate variables across partials.
- Record nesting depth — selectors deeper than 3 levels produce over-expensive compiled selectors.
- Detect `@include` calls broadening repeated magic values — these are token candidates.
- Detect whether `@use ... as *` defeats the module system.

## Edits (Stage 11)

- Prefer `@use` over `@import`; do not add new `@import` for values that belong in a shared partial.
- Prefer a real Sass variable in a shared tokens partial over a mixin repetition; mixins organise, tokens encode.
- Avoid mixins that hide a magic number used in only one place — a constant with a comment is clearer.
- `@extend` shares selectors aggressively and can produce heavy compiled output; only `@extend` placeholder selectors (or aria-style shared abstract classes) — not concrete classes that may grow.
- Selector nesting at 3+ levels tends to escalate specificity — flatten with `&` composition, or split selectors.

## Validation (Stages 12-14)

- Audit the *compiled* CSS, not only the partials: a clean `_partial.scss` can still emit `!important` wars and specificity escalation.
- Diff compiled file size as a proxy for unintentional output growth.
- Confirm Sass partial graph still resolves — a missing partial is a build error, not a UI failure, but it blocks visual validation.