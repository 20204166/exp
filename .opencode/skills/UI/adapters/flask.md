# Adapter — Flask

How Stage 1/11/12-14 differ for Flask templates (usually Jinja via Flask's loader). Use with `packs/frameworks/jinja-django-flask-fastapi.md`.

## Surface discovery (Stage 1)

- Templates live under `templates/` by default; the app may override the loader to add additional dirs.
- `{% extends %}` / `{% include %}` / `{% import %}` macros are valid (the adapter is the same as the Jinja adapter for those).
- Static assets via `url_for("static", filename=...)` from `static/` by default.
- Map blueprints — a blueprint often owns a sub-tree of templates with its own base.
- Server-rendered context comes from view functions; record the keys the surface depends on (`errors`, `form`, `is_submitted`, etc.).

## Edits (Stage 11)

- A visual change in a shared blueprint template affects every view that extends it — surface map must include all blueprint views that share the base. Do not edit a global base for a single-view fix.
- WTForms rendering has its own widget layer; reuse widget styles before overriding `{{ form.field }}` output ad hoc.
- `url_for("static", ...)` URLs include cache-busting query strings when the app sets them — do not replace with hand-written paths.
- Flask flash messages have visual categories (`success`/`error`/`info`); reuse the category CSS rather than re-inventing.

## Validation (Stages 12-14)

- Capture the surface with the Flask test client providing varying response contexts (errors / success / no-flash).
- For WTForms, validate the rendered DOM with form errors attached to non-field-errors vs field-errors — both classes matter for accessibility.