# Adapter — FastAPI templates

How Stage 1/11/12-14 differ for FastAPI-rendered templates (typically `Jinja2Templates`). Use with `packs/frameworks/jinja-django-flask-fastapi.md`.

## Surface discovery (Stage 1)

- FastAPI serves templates through `Jinja2Templates(directory=...)`; record the directory configuration and any custom `env` filters/globals.
- Map the route handler that returns `TemplateResponse(...)`; its `context` is the data surface depends on.
- Many FastAPI apps use pure JSON routes + a JS frontend; record whether the surface is HTML-served or JSON-consumed — the latter disables most of this skill's render-validation stages and pushes to JS/React adapter instead.
- `{% extends %}` / macros / includes / static assets as Jinja once Jinja2Templates is in play.

## Edits (Stage 11)

- The route handler's context is the contract; do not add keys to the response purely to drive visual state — that drifts the API. Visual state should come from boolean fields the surface already exposes, or be derived in-template safely from existing data.
- JSON-returning views are an API change — route to BugGuard, do not quietly change response shape.
- Static files via `StaticFiles` mount; reuse the mount, do not add raw `/static/...` paths to templates.
- Async template rendering is not blocking by default in FastAPI; do not introduce sync DB calls inside templates to "fix" a visual state.

## Validation (Stages 12-14)

- For HTML routes, use FastAPI's `TestClient` to render with controlled context.
- For JSON routes that drive a JS UI, switch to the React/Vue/etc. adapter for the render-validation side; the FastAPI route only validates the contract and BugGuard owns behaviour.