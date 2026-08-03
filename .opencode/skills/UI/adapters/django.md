# Adapter — Django templates

How Stage 1/11/12-14 differ for Django templates. Use with `packs/frameworks/jinja-django-flask-fastapi.md`.

## Surface discovery (Stage 1)

- Map base templates and the `{% extends %}` chain.
- `{% include %}` partials, `{% block %}` override points, and template tags from third-party apps (e.g. `django-widget-tweaks`, `django-crispy-forms`).
- Form rendering lives in form widgets, not only the template — record widget templates and renderer overrides if the project has them.
- Static files are via `{% static %}`; map the asset pipeline (collectstatic targets, postcss/scss build if any).
- Map form classes that render on the surface — the field order/labels/errors are data, but the rendering attributes are part of the surface.

## Edits (Stage 11)

- Styling forms touches widget attrs via `Form.field.widget.attrs`; changing form field definitions or validation rules is BugGuard territory.
- `{% csrf_token %}` placement is security-critical; do not move it for visual reasons. Move the *container* markup, not the token markup.
- Crispy-forms / widget-tweaks template tags have their own component conventions; reuse before introducing hand-rolled HTML.
- Avoid duplicate template branches; Django's ORM-rendered `{{ form.errors }}` already exposes error states — style its output, do not duplicate it.

## Validation (Stages 12-14)

- Render the form bound and unbound, with and without errors — the form's state matrix is `empty / filled / errors / submit-success`.
- For admin surfaces, validate against Django admin's built-in responsive CSS (admin has its own design language; do not redesign its components en masse without the `implement design` mode).
- Confirm `widget.attrs["class"]` changes survive form re-instantiation — class lost on `is_valid()` re-render is a common regression.