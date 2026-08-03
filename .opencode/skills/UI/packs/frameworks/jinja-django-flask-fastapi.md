---
pack: frameworks.jinja-django-flask-fastapi
version: 2026-07
authorities:
  - Django templates docs
  - Jinja docs
  - Flask templating
  - FastAPI Jinja2Templates
load_when:
  - template-rendered backend (django/flask/fastapi/jinja)
rules:
  - Templates are server-rendered; surface = base + extends + includes + macros
  - Static JS/CSS live in static asset dirs, not alongside templates
  - State matrix reflects server-rendered states (errors, success, loading from HTMX/inertia/SPA islands)
  - CSRF tokens, form fields, and widget rendering belong to backend semantics -> BugGuard boundary where they change meaning
validation_checks:
  - surface map includes base, extends, includes, macros
  - static asset dir CSS wired to the templates
  - states rendered through template conditionals or JS interop
false_positives:
  - XSS whiltelisting of |safe filter — may be valid; review whether output is trusted
anti-patterns:
  - inline <style> per template that duplicates static CSS
  - hardcoding CSRF token markup instead of template tag
  - server-rendering visual-only state when the JS layer should hold it
framework_notes:
  - Django: forms render via widgets; styling widgets extends the project's form theming
  - HTMX/inertia-style islands mix server-rendered with client-rendered states — record both in the state matrix
---

# Pack: Jinja / Django / Flask / FastAPI

Server-rendered templates are UI surfaces too. Django explicitly separates templates from static assets; Jinja supports reusable macros and imports. The surface map must include base templates, `{% include %}` / `{% extends %}` / macros, and the static CSS/JS entrypoints that wire into the templates.

State matrix mixes server-side context (errors, success, validation feedback) with client-side interactivity (HTMX, Alpine, vanilla JS islands). Record both branches in the surface map and the change plan.

Form rendering in Django uses widgets; a UI change to forms often expects the widget layer to be styled, not the raw template. Changing the widget is a backend boundary — route to BugGuard when widget changes alter the rendered field's `name`/value/CSRF semantics.