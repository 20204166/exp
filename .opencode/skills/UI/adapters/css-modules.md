# Adapter — CSS Modules

How Stage 1/11/12-14 differ for CSS Modules. Use with `packs/frameworks/css-modules.md`.

## Surface discovery (Stage 1)

- Detect `.module.css` / `.module.scss` files imported by the touched components.
- Map `composes:` chains: do they compose from a shared `tokens.module.css`/`shared.module.css`? Or local-composed duplicates?
- Map `:global()` selectors — usually rare; record each.
- Map `:hover` / `:focus-visible` / `data-*` selectors within modules; the scoping attribute is added automatically.
- Detect any imports of `styled`/`class-names` runtime helpers, since they interop with CSS Modules and may add non-scoped classes too.

## Edits (Stage 11)

- Composition via `composes: <class> from "../tokens.module.css"` is the preferred reuse path.
- Adding a raw local class for a value that exists as a token = duplicate-value debt; prefer composition.
- `:global()` blocks escape scoping — measure leak carefully; intended only for genuinely global set of styles (e.g. a third-party override).
- Combining a CSS Module class with a global utility class (e.g. `className={`${styles.btn} util-gap-4`}`) is fine but record both — the rendered HTML mixes scoped and global class names so specificity is summed.

## Validation (Stages 12-14)

- Inspect compiled selectors to confirm scope handles (`*_module_*__class_*` or hashed); confirm no `:global()` escapes were introduced unintentionally.
- `composes:` chains emit multiple class names; capture the rendered DOM, not the source `.module.css` file, when judging specificity.
- CSS Modules `:hover`/`:focus-visible` keep specificity low — they should not escalate. Confirm no `!important` was added inside the module.