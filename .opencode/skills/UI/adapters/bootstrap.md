# Adapter — Bootstrap

How Stage 1/11/12-14 differ for Bootstrap. Use with `packs/frameworks/bootstrap.md`.

## Surface discovery (Stage 1)

- Detect Bootstrap major version (5.x most common; v4 still in projects).
- Map the override file: Sass customisation (`_variables.scss`, `_custom.scss`) vs runtime CSS custom properties (`:root` overrides / `data-bs-theme`).
- Map component classes used on the surface (`navbar`, `card`, `table`, `modal`, `form-*`, `btn-*`, `alert`).
- Map state classes Bootstrap manages (`active`, `disabled`, `show`, `collapsed`, `is-invalid`, `is-valid`).
- Map utility-class usage (`d-flex`, `gap-*`, `mw-*`, `text-*`).
- Any aggregated overrides via `_mytheme.scss` partials should be inventoried.

## Edits (Stage 11)

- Bootstrap is component-first — prefer component class changes + Sass/CSS-var overrides over hand-rolled CSS.
- Sass overrides affect build output; CSS custom properties affect runtime theming (including dark mode via v5 `data-bs-theme`). Pick the right layer.
- Do not bypass `is-invalid` / `is-valid` form validation classes with hand-rolled error styles — Bootstrap's JS form validation hooks them.
- Modal/dropdown/tab/nav-tab JavaScript depends on `data-bs-*` attribute hooks; do not replace them with arbitrary data attributes for a visual fix.
- Custom components must reuse Bootstrap's state classes (`show`, `active`) to remain compatible with the framework's JS.

## Validation (Stages 12-14)

- Bootstrap's responsive grid (`container`, `row`, `col-*`) has breakpoints defined as Sass; capture each Bootstrap breakpoint (sm/md/lg/xl/xxl = 576/768/992/1200/1400 px).
- Bootstrap components render their accessibility semantics via the JS plugin (modal focus trap, dropdown keyboard model); capture post-init DOM, not raw template.
- Dark theme in v5 toggles via `data-bs-theme="dark"` — capture both directions to verify contrast.