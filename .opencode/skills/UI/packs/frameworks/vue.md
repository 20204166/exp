---
pack: frameworks.vue
version: 2026-07
authorities:
  - Vue docs
  - MDN accessibility for Vue
load_when:
  - vue detection
rules:
  - SFC style blocks (scoped vs not) govern CSS architecture
  - `class` and `:style` bindings reflect state — do not rewire state for a visual change
  - Composables may drive reactive UI state; track them in the surface map
validation_checks:
  - scoped vs unscoped styles correctly mapped
  - composables that drive a touched state are inventoried
  - v-model wiring preserved for forms
false_positives:
  - "scoped style leakage" via `:deep()` may be intentional for shared component styling — review
anti-patterns:
  - adding unscoped styles to override scoped defaults
  - inline :style as a substitute for tokens
framework_notes:
  - Vue `v-bind` in CSS is reactive; misuse causes re-render loops (perf boundary -> BugGuard)
---

# Pack: Vue

Vue SFCs place markup, script, and style in one file. CSS architecture depends on the `<style>` block: scoped (data attribute), not scoped, or `<style module>` for CSS Modules, or `<style scoped>` with `:deep()` for cross-boundary overrides.

State lives in reactive refs/computed/composables and `v-model`. A visual change should reuse existing reactive state; do not add state solely to drive a hover.

CSS-in-JS-equivalent in Vue (`v-bind` in `<style>`) is reactive and can cause re-render loops if wired to volatile values; that is a perf boundary with BugGuard.