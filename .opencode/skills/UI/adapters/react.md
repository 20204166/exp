# Adapter — React

How surface discovery, edits, and validation differ for React surfaces. Use with `packs/frameworks/react.md`.

## Surface discovery (Stage 1)

Map the component *tree* underneath the surface, not just one file:

- route component + layout shell
- slot-rendering children
- shared components (Button, Card, Field, ...)
- props that drive visual state (open/closed, loading, disabled)
- store / context that drives cross-component state
- the chosen CSS mechanism (CSS Modules, CSS-in-JS, Tailwind, styled-components, vanilla)

Record the chosen CSS mechanism in `surface-map.json.styles` — a React surface rarely has only one way to attach styles.

## Edits (Stage 11)

- Reuse existing component variants before adding style overrides.
- Prefer a token change to a CSS-in-JS template change.
- Do not move state from props to internal state purely for visual reasons.
- Do not change component file boundaries for visual fixes; that is refactor work and may cross the BugGuard boundary if business logic is entangled.
- CSS-in-JS template strings hide the resulting CSS class names — when reviewing specificity, instrument the rendered DOM, not just the JSX.
- `styled-components` / `emotion` may inject styles at runtime; review insertion order if specificity looks wrong.

## Validation (Stages 12-14)

- Storybook stories are evidence surfaces for the state matrix — capture them as part of evidence if present.
- React 18+ StrictMode double-invokes effects; capture focus and state traces with StrictMode-aware fixtures.
- For CSS-in-JS, run a real DOM render before asserting styles exist — template strings cannot be statically parsed as proof of applied style.
- Web font loading still causes layout shift; do not treat "components render" as a layout-stability pass.