---
pack: frameworks.bootstrap
version: 2026-07
authorities:
  - Bootstrap docs
  - Bootstrap Sass customization
load_when:
  - bootstrap detection
rules:
  - Bootstrap is component-first; customization via Sass variables and CSS custom properties
  - Override convention: Sass for build-time, CSS custom properties for runtime theming
  - Component conventions (navbar, card, table, modal, alert, form-* controls) carry built-in state classes (active, disabled, show)
  - Utility classes (spacing, display, flex) complement components
validation_checks:
  - Sass overrides in `_variables.scss` / theme overrides; CSS custom properties in `:root`
  - component state classes preserved (`active`, `disabled`)
  - utility override chains intentional, not patchwork
false_positives:
  - "inline style overrides" on a single page may be valid (e.g., per-page hero)
anti-patterns:
  - mixing `!important` overrides to fight Bootstrap specificity
  - introducing third-party component overriding Bootstrap semantics without redesign plan
  - hand-rolling what `form-*` classes already provide
framework_notes:
  - Bootstrap variable override -> Sass layer; runtime theme switch -> CSS custom properties
---

# Pack: Bootstrap

Bootstrap exposes customization through Sass variables (build-time) and CSS custom properties (runtime theming). The two layers coexist; using both for the same role creates drift.

Discovery maps the Bootstrap version, the override file (`_variables.scss` / `_custom.scss` / `:root` custom properties), and the components used on the surface. Audit checks built-in state classes (`active`, `disabled`, `show`, `collapsed`) are preserved and that overrides do not bypass the component's accessibility semantics (e.g. dropdown's keyboard model).

Don't introduce a third-party React/Vue bootstrap replacement for a UI fix alone. If that's what the change needs, it's a redesign — escalate to `implement design` mode.