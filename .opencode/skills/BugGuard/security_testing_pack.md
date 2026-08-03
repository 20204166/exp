# Security Testing Pack

Mandatory for every Mode D run. This pack defines how Mode D and its reviewers safely prove, disprove, and challenge security claims.

## How to use

Before creating or running any test, state:

```text
Security claim being tested:
Test type (from the seven types below):
What a pass would prove:
What a fail would disprove:
What a timeout/error means:
```

After the test, record in the reviewer's own artifact section:

```text
Test path:
Command:
Result:
Interpretation:
Limitations:
```

## Seven test types

Mode D distinguishes seven test types. Each has a different purpose and different ownership:

| Type | Owner | Purpose | Lives under |
|---|---|---|---|
| Security PoC | Main auditor | Demonstrate a suspected weakness | `docs/security_reviews/poc/SEC-.../` |
| Exploitability counter-test | Opposer 1 | Disprove exploitability or impact | `docs/security_reviews/poc/SEC-.../opposer1_*.py` |
| Control-verification test | Opposer 2 | Verify an existing control already handles the concern | `docs/security_reviews/poc/SEC-.../opposer2_*.py` |
| Architecture/failure-mode test | Opposer 3 | Prove fail-open, bypass, or severity overstatement | `docs/security_reviews/poc/SEC-.../opposer3_*.py` |
| Standards-semantics test | Opposer 4 | Verify external guidance really applies to the repo | `docs/security_reviews/poc/SEC-.../opposer4_*.py` |
| Agent 5 evidence test | Agent 5 | Resolve contradiction or missing evidence | `docs/security_reviews/poc/SEC-.../agent5_*.py` |
| Permanent regression test | Mode A only | Prevent regression after a fix is applied | `app/tests/` or `tests/` |

**A permanent regression test requires a transition to Mode A.** Mode D counter-tests are evidence, not repo tests. D-audit never adds files to `app/tests/` or `tests/`.

## Current reviewer-owned test rules (preserved)

This pack preserves the existing BugGuard test ownership rules:

- Opposers create their own tests
- Opposers run their own tests
- Opposers interpret their own results
- Opposers write their evidence directly into their own artifact sections
- Agent 5 creates and runs its own evidence test where appropriate
- The main auditor does not backfill reviewer tests or findings
- General chat output is not a substitute for a test artifact + written evidence

## Test categories

### Security PoCs

A security PoC demonstrates that a suspected weakness is reachable.

- Start from a confirmed entry point in repo code
- Use realistic attacker preconditions
- Assert the specific security property that fails
- Record the exact code path from entry to impact
- A PoC that fails to reproduce is evidence *against* the concern, not a test error

### Exploitability tests (Opposer 1)

Challenge whether the PoC actually demonstrates exploitability.

- Try alternative preconditions that make the attack harder
- Try with reduced attacker capabilities
- Check whether a control blocks the attack path
- Check whether the impact is real or theoretical
- If the counter-test shows the attack is not reachable, record it honestly

### Control-verification tests (Opposer 2)

Verify whether an existing control already handles the concern.

- Trace the repo code path that the PoC claims is vulnerable
- Check for middleware, decorators, dependency injection, or query filters
- Check for existing tests that cover this path
- If a control exists and is effective, the concern is an existing sufficient control

### Bypass and architecture tests (Opposer 3)

Test whether a control can be bypassed or fails open.

- **Bypass test**: can the control be circumvented via an alternate path?
- **Fail-open test**: does the control deny access on error or allow it?
- **Negative authorization test**: does an unauthorized user get denied?
- **Cross-user test**: can user A access user B's data?
- **Cross-tenant test**: can tenant A access tenant B's data?
- **Object-ownership test**: does the query filter by the requesting user's ID?
- **Privilege-transition test**: can a regular user escalate to admin?
- **Secondary-effect test**: does the hardening proposal break another control?

### Standards-semantics tests (Opposer 4)

Verify whether external guidance really applies to the repository.

- Does the OWASP cheat sheet apply to this framework/version?
- Does the OAuth BCP recommendation match the repo's OAuth flow?
- Does the NIST guidance match the repo's authentication implementation?
- Does the framework's documented behaviour match the repo's assumption?
- If external guidance does not apply, it is not proof of a vulnerability

### Agent 5 evidence tests

Resolve contradiction or fill missing evidence.

- Use only when reviewers disagree or evidence is inconclusive
- Test the specific point of contradiction
- Record what the result resolves
- Agent 5 does not replace missing reviewer sections

### Specific test patterns

#### CSRF tests

- Verify CSRF token is present in every POST/PUT/DELETE form
- Verify CSRF middleware rejects missing/invalid tokens
- Verify CSRF-safe redirect for state-changing GET requests
- Verify multipart upload CSRF handling

#### CORS tests

- Verify CORS origins are explicit, not wildcard
- Verify preflight response does not leak credentials
- Verify cross-origin requests without credentials are rejected if the endpoint requires auth

#### Session and cookie tests

- Verify Secure flag is set in production
- Verify HttpOnly flag is set
- Verify SameSite is set (Strict or Lax)
- Verify session invalidation on logout
- Verify session token rotation after privilege change

#### Token-lifecycle tests

- Verify OAuth tokens are encrypted at rest
- Verify token refresh does not leak tokens
- Verify token revocation is effective
- Verify expired tokens are rejected

#### Upload and storage-isolation tests

- Verify magic-byte detection rejects spoofed extensions
- Verify file size limits are enforced
- Verify storage paths do not allow path traversal
- Verify SHA-256 dedup prevents object collisions
- Verify local storage does not serve uploaded files from a public directory

#### Path-traversal tests

- Verify file paths are sanitized
- Verify `..` sequences are rejected
- Verify absolute paths are rejected
- Verify symlinks are not followed

#### SSRF tests

- Verify external URL inputs are validated against an allowlist
- Verify internal IPs are blocked
- Verify redirect following does not reach internal services

#### Injection tests

- Verify SQL injection via ORM parameterization
- Verify template injection via Jinja2 autoescape
- Verify command injection via subprocess parameterization
- Verify no raw string formatting reaches a query or shell

#### Output-encoding tests

- Verify HTML output is autoescaped
- Verify JSON API responses use proper content-type
- Verify error messages do not reflect user input

#### Rate-limit and abuse-resistance tests

- Verify rate limiting exists on auth endpoints
- Verify login rate limiting does not lock out legitimate users
- Verify API rate limiting prevents enumeration
- Verify webhook endpoints are not vulnerable to replay

#### Webhook replay and signature-verification tests

- Verify Stripe webhook signature verification
- Verify replay attacks are rejected
- Verify webhook idempotency

#### Retry, idempotency, and duplicate-execution tests

- Verify Celery task retries do not duplicate side effects
- Verify idempotency keys prevent duplicate payments
- Verify partial failure does not leave inconsistent state
- Verify duplicate job detection

### Local evidence vs staging evidence vs prohibited production testing

- **Local evidence**: tests run in the dev/test environment with the repo test suite. This is the primary evidence source.
- **Staging evidence**: tests run against a staging environment if the repo has one. Must be explicitly approved.
- **Prohibited production testing**: never call live Stripe, R2/S3, Sentry, OAuth, email, provider, browser-submit, or payment endpoints. Never test against real user data.

### Test-data safety

- Do not use real user data in tests
- Do not include real secrets, tokens, or credentials in test fixtures
- Do not print secrets, env values, API keys, tokens, cookies, OAuth material, raw provider payloads, raw OCR text, email bodies, user uploads, DB rows, private URLs, or full raw logs
- Redact all sensitive data in test output

### Evidence redaction

All test artifacts and written evidence must redact:
- Secrets, tokens, passwords, API keys
- Session cookies, OAuth tokens
- Raw OCR text, raw email bodies, raw provider payloads
- User PII (email, name, address)
- Database row contents
- Internal URLs not relevant to the evidence

### Contradiction handling

If test evidence conflicts:

- Compare test intent against the claimed security property
- Distinguish PoC failure from property violation
- Distinguish severity from existence
- Distinguish a narrow gap from a broad claim
- Escalate if the contradiction is non-obvious or unresolved

If evidence cannot answer the decisive question, mark `Needs more evidence` instead of guessing.

### Reproducibility

- Record the exact command, input, and environment
- Record timing if relevant
- A test that cannot be reproduced is weak evidence
- A timeout, skip, or missing dependency is not a pass

### Proof versus theoretical concern

- A security PoC that demonstrates a reachable, exploitable path is proof
- A code pattern that looks insecure but has no reachable attack path is a theoretical concern
- A theoretical concern is a hardening opportunity, not a vulnerability
- External standards define expected properties; they do not prove repo-specific exploitation

### Safe handling of exploit details

- Do not include working exploit payloads that could be used directly against a production deployment
- Use redacted or sanitized payloads in written evidence
- Record the PoC logic, not the weaponized payload
- Do not store real credentials or tokens in PoC files

## Primary sources

| Source | When to use | URL |
|---|---|---|
| OWASP WSTG | Security testing methodology and test cases | https://owasp.org/www-project-web-security-testing-guide/ |
| OWASP Cheat Sheet Series | Control-specific testing guidance | https://cheatsheetseries.owasp.org/ |
| NIST security testing | Testing methodology and evidence requirements | https://csrc.nist.gov/Projects/ssdf |
| Official testing-tool docs | pytest, httpx, Playwright testing semantics | (see research_link_pack.md) |
| Official framework testing docs | FastAPI/Starlette test client behaviour | https://fastapi.tiangolo.com/tutorial/testing/ |

External testing guidance defines methodology and expected test patterns. Repo truth (current code, tests, runtime output) is the final authority for repository behaviour.
