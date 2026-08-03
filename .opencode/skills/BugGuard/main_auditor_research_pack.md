# Main Auditor Research Pack

## Purpose

Focused official-doc research guidance for the BugGuard main auditor in Mode A and Mode B.

Use this pack to:

- write better Mode A tests or Mode B candidate-scoped evidence artifacts
- choose correct validation commands
- avoid hallucinating framework/tool semantics
- understand static typing, formatting, and linting expectations
- verify external behaviour only when it affects the current repo claim or patch

This pack does not replace repo truth. Current repo files, tests, LR output, runtime output, and BugGuard evidence always win for repo behaviour.

## Mode B test boundary

For Mode B, references to tests mean candidate-scoped PoC or counter-test evidence artifacts under `docs/bug_hunts/poc/BUG-YYYYMMDD-NNN/` unless the workflow explicitly transitions to Mode A.

Mode B does not edit app code or normal repo tests. Permanent regression tests belong to Mode A after user approval.

## When to use

Use this pack when:

- writing or reviewing Python tests
- changing or validating Python code
- interpreting Pyright, mypy, Ruff, pytest, or LR/static output
- reviewing Rust/native/frontend/build surfaces
- validating TypeScript/JavaScript/browser automation semantics
- checking framework/library behaviour that affects a bug claim or patch safety
- deciding whether an external docs/API semantics issue requires Agent 4 or Agent 5

Do not use this pack for every tiny edit if repo truth and targeted tests are enough.

## Research priority

1. Current repo code/tests/runtime output
2. Repo docs/contracts
3. LR/drift/static/test output
4. Official language/framework/tool docs
5. Official GitHub/project docs or changelogs
6. High-quality project release notes
7. Community issues/discussions only if official docs are missing and the user explicitly allows broader research

Never use random blogs/forums as primary proof.

## Python / pytest

Use official docs for:

- pytest assertions, fixtures, monkeypatch, caplog, tmp_path
- unittest.mock / MagicMock / patch semantics
- Python exception handling
- Python logging
- pathlib / os / subprocess semantics
- typing behaviour when needed

Use when:

- writing Mode A regression tests or Mode B PoC/counter-test artifacts
- checking whether a mock/test actually exercises the claimed path
- validating exception/logging behaviour
- deciding whether a test is too broad or too implementation-specific

## Static typing / lint / formatting

Use official docs for:

- Pyright configuration and diagnostics
- mypy configuration and type-checking semantics
- Ruff formatter/linter behaviour
- Ruff format compatibility
- import sorting / lint rules if the repo uses them

Default validation preference for Python changes:

- `ruff format --check .`
- `mypy app`
- `pyright`

Do not assume `lr static` covers these unless repo evidence proves it.

## FastAPI / Starlette / web surface

Use official docs for:

- routing
- dependency injection
- Request/Response behaviour
- middleware
- sessions/cookies
- CSRF/CORS assumptions only if the repo actually uses matching middleware
- background tasks
- exception handlers
- status codes and redirects

Use when:

- route/payload/schema/status-code behaviour matters
- auth/session/admin/CORS/CSRF boundaries are touched
- middleware order or error handling is part of the bug claim

## SQLAlchemy / Alembic / DB

Use official docs for:

- session/transaction semantics
- rollback/commit behaviour
- relationship loading
- constraints/indexes
- migration generation/runtime
- SQLite/Postgres differences when relevant

Use when:

- persistence, partial commits, rollback, migrations, or DB constraints are part of the claim

## Celery / Redis / jobs

Use official docs for:

- task retry semantics
- idempotency assumptions
- broker/result backend behaviour
- timeout/failure handling
- scheduling/beat semantics

Use when:

- worker/job/runtime behaviour is part of the claim

## Browser automation / Playwright

Use official docs for:

- locator semantics
- timeouts
- navigation
- form submission
- downloads/uploads
- browser context/session behaviour
- network interception
- final-submit/CAPTCHA/2FA/user-review boundaries

Use when:

- assisted-submit/browser automation behaviour is touched
- test failures involve browser timing or selectors

## Rust / Cargo / rustfmt / native

Use official docs for:

- Rust language/reference basics when semantics matter
- Cargo commands and workspaces
- rustfmt formatting behaviour
- clippy if the repo uses it
- PyO3 / maturin / native bridge docs if present in the repo

Use when:

- native/build/Rust code is touched
- Rust formatting/check commands are needed
- Python/native boundary behaviour affects the bug claim

Suggested checks only when repo truth says Rust/native is relevant:

- `cargo fmt --check`
- `cargo check`
- `cargo test`
- `cargo clippy` if the repo uses it

Do not invent native commands if the repo does not document or contain them.

## TypeScript / JavaScript / frontend

Use official docs for:

- TypeScript compiler behaviour
- npm/pnpm/yarn scripts from repo package files
- ESLint/Prettier if the repo uses them
- Vite/React/build tool docs if present
- browser API docs from MDN when relevant

Suggested checks only when repo truth says frontend/native is relevant:

- repo-defined `npm` / `pnpm` / `yarn` scripts
- TypeScript check script from `package.json`
- test/build script from `package.json`

Do not invent frontend commands.

## GitHub / GitHub Actions / CI

Use official GitHub docs for:

- GitHub Actions workflow syntax
- permissions
- secrets handling
- checkout/cache semantics
- matrix behaviour
- artifact upload/download
- branch/path filters

Use when:

- CI/workflow/tooling bug claims depend on GitHub Actions semantics

Do not scrape GitHub issues/discussions by default. Use official GitHub docs first.

## Security guidance

Use official or authoritative guidance for:

- OWASP
- NIST
- framework security docs
- provider security docs

Use when:

- auth/session/admin/CSRF/CORS/privacy/redaction/secrets/webhook/payment boundaries are part of the claim

External security guidance can support severity and expected controls, but repo code/tests/runtime evidence must prove the repo-specific bug.

## Main auditor research discipline

Before external research, state the exact question:

```text
Research question:
Repo evidence that triggered it:
Official source needed:
How this could change the test or final decision:
```

After research, record:

```text
Source type: official docs / release notes / standard / other
Finding:
Repo-specific implication:
Local evidence still needed:
```

Do not paste long quotes or broad research notes into BugGuard ledgers. Keep only the finding needed for the decision.

## Quick-reference URLs

Must-check official docs when framework/tool semantics matter:

- Python docs: https://docs.python.org/3/
- pytest docs: https://docs.pytest.org/en/stable/
- FastAPI docs: https://fastapi.tiangolo.com/
- SQLAlchemy docs: https://docs.sqlalchemy.org/en/latest/
- Rust docs: https://doc.rust-lang.org/book/

Secondary search:

- Stack Overflow (search by framework/tool/error): https://stackoverflow.com/

For any framework, tool, library, or provider not listed above, search for its official documentation site directly — main auditor may use whatever official docs are needed. The URLs here cover the most common Python/web/test surfaces; everything else (Rust, TypeScript, Celery, Playwright, GitHub Actions, etc.) can be found by searching.

## When to escalate to Agent 4 / Agent 5

Escalate to Agent 4 when:

- official framework/library/API semantics are decisive
- main auditor cannot confidently interpret docs
- external semantics may disprove or downgrade the claim

Escalate to Agent 5 when:

- full B7 is selected
- selected opposers disagree
- candidate is P0/P1/P2
- security/privacy/fail-closed/evidence-integrity is involved
- main auditor cannot decide after synthesis
