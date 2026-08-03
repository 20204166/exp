# Adapter — Jinja

How Stage 1/11/12-14 differ for Jinja templates. Use with `packs/frameworks/jinja-django-flask-fastapi.md`.

## Surface discovery (Stage 1)

- Map base template (`{% extends "base.html" %}`), blocks (`{% block content %}`), includes (`{% include "_partial.html" %}`), and macros (`{% macro field(name) %}...{% endmacro %}`).
- Map the import graph (`{% import "forms.html" as forms %}`) and the macros actually called on the surface.
- Static assets are wired through the app's static dir convention; map the CSS entry and any per-template `<style>` blocks.
- Server-rendered state lives in template variables — record which variables drive visual branches (`has_errors`, `is_loading`, etc.).
- Track JS / Alpine / HTMX islands that add client-side states.

## Edits (Stage 11)

- Avoid inline `{% set %}` context manipulation to drive visual changes; if the data is wrong, the template is not the fix layer (route to BugGuard).
- Keep `{{ esc() }}` / Jinja autoescape intact — removing autoescape to render HTML is a BugGuard (security) boundary.
- Prefer a CSS class change over a new `{% if %}` branch for a visual difference; template branches that vary output for purely visual reasons tend to drift.
- `|safe` filter on dynamic input is XSS; only trusted-content `|safe` is acceptable.

## Validation (Stages 12-14)

- Test server-rendered states by varying the rendered context (fixtures/fixtures dict), not by mocking branches in the test tree.
- Validate the produced HTML, not the template source — autoescaped output and `|safe` output render differently.
- For Alpine / HTMX islands, capture both server-rendered and post-interaction DOM for the same state.