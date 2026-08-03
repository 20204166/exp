# Adapter — Vanilla CSS

How Stage 1/11/12-14 differ for vanilla CSS. Use with `packs/css/*`.

## Surface discovery (Stage 1)

- Map every CSS file loaded by the surface and its load order (link order matters under same specificity).
- Detect global styles (`*`, `body`, `html`), element selectors (`a`, `button`, `input`), class selectors, ID selectors, and selector layers (`@layer`).
- Detect cascade layer declaration (`@layer reset, base, components, utilities;`); record the order.
- Detect `@import` chains (CSS `@import` blocks loading ordering).
- Detect `!important` hotspots and `:not(...)`/`:where(...)`/`:is(...)` usage.
- Inventory "magic" px/hex values that appear 3+ times (token candidates).

## Edits (Stage 11)

- Apply the implementation-rules CSS hierarchy: token → variant → component-local → utility → global → layer → dependency.
- Prefer adding a CSS custom property to a single root block over hardcoding the same value across rules.
- Avoid `!important` for one-off wins; consider a single layer or a more specific scoped selector instead.
- Cascade layers in an existing un-layered codebase are a migration; record it as such if you introduce one.
- Inline styles (`style="..."`) on individual elements bypass the cascade entirely and are debt; do not use them to win specificity fights.

## Validation (Stages 12-14)

- Compute specificity before/after for touched selectors; never let the highest specificity escalate silently.
- Grep for new `!important` count; never let net count increase without an accepted reason.
- Confirm class leak (`@media` matches against unintended selectors) when widening selector scope.
- For animations, confirm `prefers-reduced-motion` collapses decorative transitions to instant.