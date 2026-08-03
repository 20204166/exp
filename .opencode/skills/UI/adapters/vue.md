# Adapter — Vue

How Stage 1/11/12-14 differ for Vue (3.x) surfaces. Use with `packs/frameworks/vue.md`.

## Surface discovery (Stage 1)

- Identify the SFC `<template>` / `<script setup>` / `<style>` blocks for each component on the surface.
- Map `class` and `:style` bindings that reflect state.
- Map `v-model` wiring for forms (single source of truth for value/state).
- Map composables that drive reactive UI state (`useX()`). Composables are part of the surface if a visual state depends on them.
- Record scoped vs unscoped `<style>`. Scoped adds a data attribute; `:deep()` deliberately pierces scope.
- `<style module>` (CSS Modules) and `<style scoped>` are not interchangeable; record which is in use.

## Edits (Stage 11)

- Reuse scoped style blocks within the touched component; do not add unscoped styles to override scoped defaults.
- `:deep()` is intentional for cross-boundary styling; check whether the pierced element is owned by your component or by a shared library — shared library overrides are architecture work.
- Do not change `v-model` wiring to add a hover.
- Vue `v-bind()` inside `<style>` is reactive; using it with volatile values cause re-render loops — that crosses the perf boundary to BugGuard.
- `<script setup>` and Options API can coexist; do not migrate between them for a visual fix.

## Validation (Stages 12-14)

- Inspect compiled JS to confirm class names against the rendered DOM (`<style scoped>` adds stable attributes; CSS Modules relies on module resolution).
- For reactivity-driven visuals, capture consecutive frames of the state trace so the report shows the state transition, not just frame N.
- Watch for transitions on `v-show` vs `v-if`; they have different motion semantics.