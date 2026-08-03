# Core — Surface Discovery

Stage 1. A UI surface is rarely one file. Before auditing, build the full surface map and write it to `.ui/<surface-slug>/surface-map.json` (conforms to `schemas/surface-map.schema.json`).

## What a surface contains

Discover all of:

- route(s) that lead to the surface
- template(s), including base/layout shell, partials, includes, macros
- component files (framework-specific)
- CSS entrypoints + global styles + utility classes + component styles
- scripts / JS interactions
- icons / assets / fonts used by the surface
- state-specific components (loading, error, empty, etc.)
- test or story files for the surface
- design-token files that influence the surface

## Framework-specific discovery

| Stack | Extra things to map |
|---|---|
| React | component tree + props/state, CSS Modules / CSS-in-JS / Tailwind detection, Storybook stories |
| Vue | SFC `<style>` blocks (scoped vs not), `class`/`style` bindings, composables |
| Jinja/Django/Flask/FastAPI | base templates, `{% include %}` / `{% extends %}` / macros, static asset dirs, server-rendered states |
| Tailwind | `tailwind.config.*` theme tokens, responsive variants, arbitrary-value usage drift, `@layer` usage |
| Bootstrap | Sass/CSS variable overrides, component conventions, utility overrides |
| Vanilla CSS/SCSS | partials, `@import`/`@use`, global leakage, layers, partials chain |

See `adapters/` for per-stack discovery notes.

## Surface map schema (summary; authoritative in schemas/)

```json
{
  "surface": "human name",
  "slug": "machine-slug",
  "routes": ["/path"],
  "templates": ["path", "..."],
  "styles": ["path"],
  "scripts": ["path"],
  "components": ["Name"],
  "states": ["default", "loading", "error", "empty", "..."],
  "viewports": [375, 768, 1280],
  "tokens_referenced": ["--space-4", "..."],
  "accessibility_landmarks": ["header", "main", "nav"],
  "evidence_availability": "renderable | browser-automatable | code only"
}
```

`viewports` are project-specific (see `validation-rules.md` for the default matrix and how to narrow it).

## Surface discovery rules

- Do not claim a surface is mapped from the file the user named alone. Trace at least one template inheritance / include / macro chain.
- If a route renders multiple templates (base + page + partial), list all of them.
- If a component has slot children, list the slot-rendering files too.
- if evidence availability is `code only` (no renderable surface), cap confidence at Tier 1 and refuse layout/spacing claims from this evidence alone.
- If the surface depends on dynamic data, list the states the surface requires for full state matrix (Stage 4).

## Surface sampling (whole-app audits)

For `full surface refinement`, do not attempt to map every page. Sample representative surfaces:

- landing / dashboard
- form
- table / list
- detail page
- modal / dialog
- empty state
- error state
- mobile navigation
- settings / profile
- authentication page

Record the sampling rationale in `.ui/<surface-slug>/reports/ui-audit.md`. Sampling must cover both authenticated and public surfaces when both exist.

## Anti-drift

- Do not map a surface from memory. Read the files.
- If a template path or component name in the user's prompt does not exist, record the mismatch; do not guess a path.
- If discovery reveals the surface spans more than one route, the user's prompt may understate scope. Record this in the audit and widen the surface map; do not silently narrow to the named file.