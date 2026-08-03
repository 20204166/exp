---
pack: frameworks.css-modules
version: 2026-07
authorities:
  - CSS Modules spec
  - MDN CSS Modules
load_when:
  - css modules detection (e.g. `*.module.css`, `composes`)
rules:
  - CSS Modules scope class names per file; leakage is generally architecture-positive
  - `composes:` references a token or shared module; reuse is the intended path
  - Global class setup (e.g. `:global(.btn)`) is intentional and rare
validation_checks:
  - `composes:` chains traceable to a shared token module
  - `:global()` blocks minimal and intentional
  - no leakage via deep selectors
false_positives:
  - "duplicate class name across files" is intended — CSS Modules scope per file
anti-patterns:
  - mixing CSS Modules with global CSS for the same component without coordination
---

# Pack: CSS Modules

CSS Modules scope class names per file. This makes leakage less likely by construction, but `composes:` chains can carry drift (composing the same token under different names).

Discovery maps the `.module.css` files referenced by components and how they relate to a shared tokens module.

Audit checks for `composes:` chains duplicating tokens (a `composes: padding-4` plus a raw `padding: 16px` for the same role) and the rare intentional `:global()` blocks.