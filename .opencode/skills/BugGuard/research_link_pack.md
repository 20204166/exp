# BugGuard Research Link Pack

## LR command selection rule

Before choosing LR commands, run or inspect:

```bash
./lr --list
./lr impact
```

`./lr --list` is the current repo truth for available LR checks. Agents must choose commands from the list shown by the current repo, not from memory, old prompts, stale docs, or guessed check names.

Use the list to classify each relevant command as:

```text
fast read-only
medium read-only
long read-only
explicit-only
writer/apply capable
unsafe/live/external
unknown
```

Then choose the smallest safe command set that matches the suspected bug area.

Rules:

- Prefer current `./lr --list` names over hardcoded old command names.
- Do not run writer/apply commands during audit mode.
- Do not run explicit-only checks unless the user/task explicitly asks or the skill allows it.
- Do not treat a missing LR command as a pass.
- If a suggested command in this link pack is missing from `./lr --list`, skip it and report that it was unavailable.
- If `./lr impact` recommends checks, prefer those unless the suspected bug area clearly requires an additional read-only check.
- Use bespoke commands from this file only after mapping them to the current `./lr --list` output.
- If unsure, run the safest read-only baseline only and report uncertainty.

Minimum safe baseline when available:

```bash
./lr impact
./lr 7
./lr secrets
```

Add area-specific LR checks only when `./lr --list` confirms they exist and they match the bug surface.

## Bespoke command sets

Use safe read-only commands based on suspected area.

### Routes/API/auth/admin
```bash
git grep -n "APIRouter\|@router\.\|include_router\|Depends\|require_admin\|csrf\|webhook\|signature" app tests 2>/dev/null || true
python -m pytest -q tests app/tests -k "auth or admin or csrf or webhook or route" || true
```

### Storage/uploads/PDFs
```bash
git grep -n "StorageBackend\|LocalStorageBackend\|S3StorageBackend\|presigned\|upload\|pdf\|object_key\|stored_path" app scripts tests 2>/dev/null || true
python -m pytest -q tests app/tests -k "storage or upload or attachment or pdf or artifact or migration or presigned" || true
```

### Delay providers/cache/evidence
```bash
git grep -n "Delay\|DelayEvidence\|SampleDelayProvider\|STRICT_LIVE_EVIDENCE_MODE\|cache\|provider" app tests docs 2>/dev/null || true
python -m pytest -q tests app/tests -k "delay or train or rail or provider or cache or evidence" || true
```

### Auto-submit/browser/final-submit boundary
```bash
git grep -n "auto_submit\|run_browser_submit\|final_submit\|captcha\|2fa\|human gate\|submit" app native tests docs 2>/dev/null || true
python -m pytest -q tests app/tests -k "auto_submit or assisted or browser or final_submit or captcha or 2fa" || true
```

### LR/tooling/drift/deps/MCP
```bash
git grep -n "local_readiness\|drift\|surface_drift\|dependency_safety\|license\|explicit-only\|apply\|mcp" scripts tooling tools tests docs 2>/dev/null || true
python -m pytest -q tests app/tests -k "local_readiness or drift or dependency or license or mcp" || true
```

### Security/privacy/redaction
```bash
git grep -n "redact\|sensitive\|privacy\|secret\|token\|password\|cookie\|oauth\|provider payload\|ocr" app tests scripts docs 2>/dev/null || true
python -m pytest -q tests app/tests -k "redaction or privacy or sensitive or secret or logging" || true
```

## Research Link Pack

Agent 4 and Agent 5 should use this curated link pack before broad web searching.

Official docs are primary evidence. Stack Overflow, GitHub Issues, issue trackers, and blog posts are secondary discovery tools only. Secondary sources may suggest a failure mode, search term, workaround, or reproduction command, but they do not prove a bug unless repo evidence and official docs also support it.

Agent 5 must use the relevant parts of this pack and record what it used in the opposition file.

### Agent 5 Validated Search Set

Agent 5 must run a structured search, not a random search.

For each candidate bug, Agent 5 should choose the relevant stack and search in this order:

```text
1. repo evidence and prior bug hunts
2. LR docs, ./lr --list, and LR/drift outputs
3. official language docs
4. official framework/library docs
5. official tool docs
6. official changelogs/release notes/migration guides
7. official security guidance/advisories
8. GitHub Issues or project issue trackers as secondary clues
9. Stack Overflow as secondary clues
10. broader web only if the above do not explain the failure mode
```

Agent 5 should write the exact searches it used:

```text
official docs query:
repo grep query:
LR/drift command:
issue-tracker query:
Stack Overflow query:
what evidence changed the decision:
```

### Agent 5 required search patterns

Use these patterns and adapt the terms to the suspected bug:

```text
<language/framework> <error text> official docs
<library/tool> <exit code or exception> official docs
<framework> <function/class/setting> regression issue
<tool> <command> <flag> behavior docs
<database/tool> <lock/transaction/migration> docs
<package> changelog breaking change <version>
<package> GitHub issue <error text>
Stack Overflow <tool/framework> <exact error text>
site:stackoverflow.com/questions/tagged/<tag> <exact error text>
```

Agent 5 must include at least one search for sibling bugs:

```text
same config key elsewhere
same exception handling pattern elsewhere
same timeout/retry pattern elsewhere
same env var in docs/examples/tests
same migration/DDL pattern elsewhere
same route/auth/session pattern elsewhere
same frontend build/runtime pattern elsewhere
same native/Rust/Python boundary pattern elsewhere
```

### Language docs

```text
Python documentation:    https://docs.python.org/3/
Python subprocess:       https://docs.python.org/3/library/subprocess.html
Python asyncio:          https://docs.python.org/3/library/asyncio.html
Python pathlib:          https://docs.python.org/3/library/pathlib.html
Python logging:          https://docs.python.org/3/library/logging.html
Python exceptions:       https://docs.python.org/3/library/exceptions.html
JavaScript MDN:          https://developer.mozilla.org/en-US/docs/Web/JavaScript
TypeScript handbook:     https://www.typescriptlang.org/docs/handbook/intro.html
TypeScript compiler:     https://www.typescriptlang.org/tsconfig/
CSS MDN:                 https://developer.mozilla.org/en-US/docs/Web/CSS
Tailwind CSS:            https://tailwindcss.com/docs
Rust book:               https://doc.rust-lang.org/book/
Rust std lib:            https://doc.rust-lang.org/std/
Cargo book:              https://doc.rust-lang.org/cargo/
Clippy lints:            https://doc.rust-lang.org/clippy/
```

### General command/repo evidence

```text
pytest usage:              https://docs.pytest.org/en/stable/how-to/usage.html
pytest tmp_path:           https://docs.pytest.org/en/stable/how-to/tmp_path.html
pytest monkeypatch:        https://docs.pytest.org/en/stable/how-to/monkeypatch.html
Git grep:                  https://git-scm.com/docs/git-grep
Git diff:                  https://git-scm.com/docs/git-diff
Git status:                https://git-scm.com/docs/git-status
```

### Docker / Compose / Postgres deployment

```text
Docker Compose file:       https://docs.docker.com/reference/compose-file/
Docker Compose config:     https://docs.docker.com/reference/cli/docker/compose/config/
Dockerfile reference:      https://docs.docker.com/reference/dockerfile/
PostgreSQL docs:           https://www.postgresql.org/docs/current/
Postgres Docker image:     https://hub.docker.com/_/postgres
```

### Database / migrations / ORM

```text
Alembic commands:          https://alembic.sqlalchemy.org/en/latest/api/commands.html
Alembic tutorial:          https://alembic.sqlalchemy.org/en/latest/tutorial.html
SQLAlchemy docs:           https://docs.sqlalchemy.org/en/latest/
SQLAlchemy errors:         https://docs.sqlalchemy.org/en/latest/errors.html
PostgreSQL locking:        https://www.postgresql.org/docs/current/explicit-locking.html
SQLite docs:               https://www.sqlite.org/docs.html
```

### Web app / workers / browser automation

```text
FastAPI:                   https://fastapi.tiangolo.com/
Starlette:                 https://www.starlette.io/
Celery:                    https://docs.celeryq.dev/en/stable/userguide/
Redis:                     https://redis.io/docs/latest/
Playwright Python:         https://playwright.dev/python/docs/intro
```

### Frontend / build / Node

```text
Node.js:                   https://nodejs.org/docs/latest/api/
npm CLI:                   https://docs.npmjs.com/cli/
PostCSS:                   https://postcss.org/
MDN HTTP:                  https://developer.mozilla.org/en-US/docs/Web/HTTP
MDN Fetch:                 https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API
```

### Native / Rust / Python boundary

```text
PyO3:                      https://pyo3.rs/
maturin:                   https://www.maturin.rs/
Rust FFI:                  https://doc.rust-lang.org/nomicon/ffi.html
Setuptools:                https://setuptools.pypa.io/en/latest/
Python packaging:          https://packaging.python.org/en/latest/
```

### Security / code review

```text
OWASP Top 10:              https://owasp.org/www-project-top-ten/
OWASP ASVS:                https://owasp.org/www-project-application-security-verification-standard/
OWASP Cheat Sheet:         https://cheatsheetseries.owasp.org/
NIST SSDF:                 https://csrc.nist.gov/Projects/ssdf
CVE database:              https://www.cve.org/
GitHub Advisory DB:        https://github.com/advisories
pip-audit:                 https://pypi.org/project/pip-audit/
npm audit:                 https://docs.npmjs.com/cli/commands/npm-audit
```

### Secondary discovery only

Use these only to discover similar failure modes, terminology, reproduction ideas, or commands to verify. Do not use them as primary proof.

```text
Stack Overflow:            https://stackoverflow.com/
Stack Overflow Python:     https://stackoverflow.com/questions/tagged/python
Stack Overflow FastAPI:    https://stackoverflow.com/questions/tagged/fastapi
Stack Overflow SQLAlchemy: https://stackoverflow.com/questions/tagged/sqlalchemy
Stack Overflow Celery:     https://stackoverflow.com/questions/tagged/celery
GitHub Issues:             https://github.com/search?q=is%3Aissue&type=issues
```

When Agent 5 uses a secondary source, it must still verify the claim against official docs or repo evidence.
