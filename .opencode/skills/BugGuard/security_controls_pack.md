# Security Controls Pack

Mandatory for every Mode D run. This pack defines expected properties, failure modes, evidence requirements, and hardening considerations for application-security controls.

## How to use

For each control relevant to the current Mode D run, answer:

```text
Required security property:
Existing sufficient control? (repo evidence path)
Missing control? (what gap)
Compensating control? (what mitigates)
Recommended hardening? (scoped proposal)
Compatibility trade-off?
Usability trade-off?
Availability trade-off?
Deployment-dependent? (what config)
Configuration-dependent? (what setting)
Residual risk?
Repository-specific proof still required?
```

Repo truth is the final authority. External standards define expected properties, not repo-specific proof.

## Control classification

| Status | Meaning |
|---|---|
| **Existing sufficient** | Control exists in repo code, is effective, and is verified |
| **Existing partial** | Control exists but has a gap (e.g. missing on some paths) |
| **Missing** | No control exists; hardening opportunity or vulnerability |
| **Compensating** | Another control partially mitigates the risk |
| **Deployment-dependent** | Control exists in code but depends on deployment config |
| **Configuration-dependent** | Control exists but depends on env/settings |

## Authentication

**Required property:** only legitimate users can authenticate; failed attempts are rate-limited and do not leak information.

Verify in repo: password hashing, login rate limiting, session token generation, session expiry/rotation, email enumeration prevention, OAuth state parameter, 2FA enforcement.

Failure modes: fail open on login error, fail open on OAuth error, timing side-channel.

Primary sources: OWASP ASVS V2, NIST 800-63B.

## Authorization

**Required property:** every access to a protected resource checks the requesting user's authorization before returning data.

Verify in repo: route-level auth dependency, object-level authorization (WHERE user_id), admin authorization, enterprise membership authorization, authorization on download/API endpoints.

Failure modes: authentication without authorization (BOLA), authorization after data fetch, authorization on UI but not API.

Primary sources: OWASP ASVS V4, OWASP Top 10 A01, OWASP API Security Top 10 API1-2023.

## BOLA/IDOR

**Required property:** a user cannot access another user's objects by guessing or enumerating IDs.

Verify in repo: Trip queries filter by user_id, Claim queries join through Trip, Attachment chain, download endpoint ownership, enterprise data filtering, API endpoints filter by user_id.

Failure modes: sequential IDs allow enumeration, API accepts arbitrary object ID without ownership check, download serves by path without ownership check.

Primary sources: OWASP API Security Top 10 API1-2023, OWASP ASVS V4.2.

## Object ownership

**Required property:** every user-owned object records its owner and every access path checks ownership.

Verify in repo: Trip.user_id FK, Claim.trip_id chain, Attachment.claim_id chain, enterprise members table, background job user context.

Failure modes: ownership chain not fully traversed, background job runs without user context.

Primary sources: OWASP ASVS V4.2.

## Sessions and cookies

**Required property:** session tokens are unguessable, tied to a single user, expire appropriately, and cannot be stolen or replayed.

Verify in repo: Secure flag, HttpOnly flag, SameSite, session expiry, session invalidation on logout, token rotation after privilege change.

Failure modes: missing Secure flag, missing HttpOnly, missing SameSite, no invalidation on logout.

Primary sources: OWASP ASVS V3, OWASP Cheat Sheet (Session Management).

## CSRF

**Required property:** every state-changing request (POST/PUT/DELETE) requires a CSRF token that the attacker cannot obtain.

Verify in repo: CSRF middleware on all POST/PUT/DELETE, CSRF token in every form, multipart upload CSRF, CSRF-safe redirect, SameSite as defence in depth.

Failure modes: middleware bypassed for a route, multipart handled differently, token not regenerated after login.

Primary sources: OWASP ASVS V4.2, OWASP Cheat Sheet (CSRF Prevention).

## CORS

**Required property:** cross-origin requests are only allowed from trusted origins; credentialled requests are not sent to untrusted origins.

Verify in repo: explicit origins (not wildcard), no credentials with wildcard, preflight does not leak headers, middleware order.

Failure modes: wildcard + credentials, middleware applied after route handler.

Primary sources: OWASP ASVS V14.5, OWASP Cheat Sheet (CORS).

## CSP and browser security headers

**Required property:** the browser enforces content restrictions that prevent XSS, clickjacking, and MIME-type confusion.

Verify in repo: Content-Security-Policy, X-Content-Type-Options: nosniff, X-Frame-Options: DENY, Strict-Transport-Security, Referrer-Policy, Permissions-Policy.

Failure modes: missing CSP, missing HSTS, missing nosniff.

Primary sources: OWASP ASVS V14.4, MDN (CSP, HSTS, security headers).

## Input validation

**Required property:** all attacker-controlled input is validated before use.

Verify in repo: Pydantic schema validation on API, form validation on UI, file upload validation, URL parameter validation, JSON body validation, no eval/exec on input.

Failure modes: validation only on API not UI, validation on content but not filename, content-type manipulation bypass.

Primary sources: OWASP Top 10 A03, OWASP Cheat Sheet (Input Validation).

## Output encoding

**Required property:** all output is encoded for its destination context (HTML, JSON, URL, JavaScript).

Verify in repo: Jinja2 autoescape enabled, JSON responses use proper content-type, error messages do not reflect input unescaped, URL parameters encoded.

Failure modes: autoescape disabled on a block, user input in error page, `|safe` on user-controlled data.

Primary sources: OWASP Top 10 A03 (XSS), OWASP Cheat Sheet (XSS Prevention).

## Rate limiting and abuse resistance

**Required property:** automated attacks are slowed or blocked without locking out legitimate users.

Verify in repo: login rate limiting, API rate limiting, webhook rate limiting, upload rate limiting, account creation rate limiting.

Hardening: add rate limiting to auth (10/min login), API (60/min), Redis-based (DB 1 per production architecture).

Failure modes: no rate limiting (brute force), rate limiting that locks out users (availability regression), rate limiting on UI but not API.

Primary sources: OWASP ASVS V11, OWASP Cheat Sheet (Denial of Service).

## File uploads and storage isolation

**Required property:** uploaded files are validated, stored safely, and served only to authorized users.

Verify in repo: magic-byte detection (Rust or Python fallback), MIME+extension cross-check, SHA-256 dedup, 10MB max, path construction (no traversal), local storage not public, R2 keys user-scoped, download ownership check.

Failure modes: spoofed extension, path traversal in storage path, file served without ownership check.

Primary sources: OWASP ASVS V12, OWASP Cheat Sheet (File Upload).

## Path handling

**Required property:** file paths constructed from user input cannot escape the intended directory.

Verify in repo: path traversal protection in LocalStorageBackend, no user-controlled absolute paths, no symlink following, path sanitization.

Primary sources: CWE-22 (Path Traversal).

## Secrets and sensitive configuration

**Required property:** secrets are never exposed in logs, error messages, responses, or test output.

Verify in repo: `lr secrets` (1, 4) pass, no secrets in defaults, no secrets in error messages, no secrets in fixtures, ENCRYPTION_KEY used for OAuth tokens, SECRET_KEY not defaulted in prod.

Failure modes: secret in default env value, secret in error message, secret in log.

Primary sources: OWASP ASVS V7, NIST SSDF PO.5.

## Token lifecycle

**Required property:** tokens are generated, stored, used, and revoked safely.

Verify in repo: OAuth tokens encrypted at rest (Fernet), refresh does not leak, revocation on account deletion, session rotation after privilege change, no token in URL parameters.

Primary sources: OWASP ASVS V3.3, OAuth 2.0 Security BCP.

## OAuth

**Required property:** OAuth flows are protected against authorization code injection, CSRF, token leakage, and open redirect.

Verify in repo: state parameter (CSRF), PKCE if applicable, redirect URI exact match (not prefix), token storage encryption (Fernet), scope validation, refresh token handling, revocation on disconnect.

Failure modes: missing state (CSRF on callback), prefix-match redirect (open redirect), plaintext token (DB compromise), no revocation on disconnect.

Primary sources: OAuth 2.0 Security BCP (RFC 9700), OWASP ASVS V2.9.

## Webhooks

**Required property:** webhook endpoints verify authenticity and are replay-resistant.

Verify in repo: Stripe webhook signature verification, timestamp validation (prevent replay), idempotency (duplicate event handling), no secret in response.

Failure modes: missing signature verification (forgery), no timestamp check (replay), no idempotency (duplicate side effects).

Primary sources: OWASP Cheat Sheet (Webhook Security), Stripe webhook docs.

## Payments

**Required property:** payment operations are atomic, idempotent, and cannot be manipulated by the client.

Verify in repo: Stripe webhook idempotency, amount validation server-side (not client-trusted), customer ID ownership, no raw Stripe payload logged, webhook signature before processing.

Failure modes: client-controlled amount, missing webhook signature, duplicate payment on retry, Stripe payload logged raw.

Primary sources: OWASP ASVS V12.4, Stripe security best practices.

## Logging, audit logging, and redaction

**Required property:** security-relevant events are logged; sensitive data is never in logs.

Verify in repo: auth events logged (login, logout, failed login), admin actions logged, no secrets/tokens/passwords in logs, no raw OCR in logs, no raw email bodies in logs, no raw provider payloads in logs, no user PII in logs without justification, audit trail for claim lifecycle changes.

Failure modes: sensitive data in log, missing auth event log, missing audit trail.

Primary sources: OWASP ASVS V7 (logging and monitoring), NIST 800-92 (log management).

## Privacy and redaction

**Required property:** user data is not disclosed beyond what is necessary.

Verify in repo: OCR text never logged raw, email bodies never logged raw, Stripe payloads never logged raw, user passwords never stored plaintext, pre-signed R2 URLs not stored permanently, error messages do not leak PII.

Failure modes: raw sensitive data in log, PII in error response, data retained beyond policy.

Primary sources: OWASP ASVS V7.1, GDPR data minimisation principle.

## DB isolation and multi-tenancy

**Required property:** tenant boundaries are enforced at the data layer, not just at the route layer.

Verify in repo: enterprise queries filter by enterprise_id, enterprise membership checked before data access, no cross-tenant queries possible via API, background jobs scoped to the correct tenant.

Failure modes: query without tenant filter (cross-tenant leak), background job without tenant context, admin route that bypasses tenant filtering.

Primary sources: OWASP API Security Top 10 API1-2023, OWASP ASVS V4.3.

## Transactions

**Required property:** multi-step data operations are atomic; partial failure does not leave inconsistent state.

Verify in repo: DB commit after all side effects (not before), rollback on failure, storage cleanup on commit failure, enterprise invoice IntegrityError retry with savepoint.

Failure modes: commit before storage write (orphan blob), no rollback on error (inconsistent state), partial commit across tables.

Primary sources: SQLAlchemy transaction docs, OWASP ASVS V12.1.

## Background jobs

**Required property:** background jobs are idempotent, retryable, and do not produce duplicate side effects.

Verify in repo: Celery task idempotency, retry semantics (acks_late for PDF/browser tasks), no duplicate job execution, partial failure visibility, task result expiry.

Failure modes: non-idempotent task (double side effect on retry), silent failure (no error signal), duplicate job (same effect twice).

Primary sources: Celery docs (idempotency, retries), OWASP ASVS V12.

## Retries, idempotency, and duplicate execution

**Required property:** retried operations do not produce duplicate side effects.

Verify in repo: idempotency keys on payment operations, savepoint + retry on IntegrityError (enterprise billing), no double-write on task retry, evidence bytes cleaned up on commit failure.

Failure modes: retry produces duplicate payment, retry produces duplicate evidence, retry produces duplicate email.

Primary sources: Celery retry docs, Stripe idempotency docs.

## Secure configuration and secure defaults

**Required property:** the default configuration is safe without manual hardening.

Verify in repo: feature flags default off, SECRET_KEY not defaulted in prod, Redis auth not required in dev but available in prod, API docs disabled outside local/dev/ci, CORS explicit origins, rate limiting configurable.

Failure modes: feature flag defaults to on in prod, secret defaults to a known value, API docs exposed in prod.

Primary sources: OWASP ASVS V14, CISA Secure by Design.

## Provider boundaries

**Required property:** external provider interactions are authenticated, validated, and fail safely.

Verify in repo: delay provider API calls authenticated, provider responses validated before use, provider failure does not corrupt evidence, Gmail/Outlook OAuth tokens encrypted, no raw provider payload logged.

Failure modes: unauthenticated provider call, provider response trusted without validation, provider failure fails open (bad evidence accepted).

Primary sources: OWASP API Security Top 10 API8-2023, provider security docs.

## Browser automation and final-submit boundaries

**Required property:** the system never auto-submits to operator portals; a human is always in the loop for final submission.

This is an inviolable product rule. Security hardening must never cross this boundary.

Verify in repo: no auto-submit code path, human-gate enforcement, CAPTCHA/2FA handled by user, no operator credential storage, no portal-scraping.

Failure modes: automated submit without human review, credential storage for operator portals, CAPTCHA bypass.

Primary sources: RailRefund product rules (HANDOFF.md), OWASP ASVS V11.3.

## CAPTCHA and 2FA

**Required property:** human-verification challenges are enforced where required and cannot be bypassed.

Verify in repo: CAPTCHA presence detection in browser flow, 2FA enforcement for admin accounts if applicable, no programmatic CAPTCHA solving, 2FA cannot be skipped.

Failure modes: CAPTCHA detection fails (submit proceeds without human verification), 2FA bypass via route manipulation.

Primary sources: OWASP ASVS V2.8, OWASP Cheat Sheet (Bot Management).

## Error handling and fail-open/fail-closed controls

**Required property:** security controls fail closed; errors do not leak information.

Verify in repo: authorization check fails closed, CSRF fails closed, session validation fails closed, webhook verification fails closed, storage fails closed (reject upload, not silently accept), OCR fails closed (reject claim, not submit with bad data).

Failure modes: any security control that fails open.

Primary sources: OWASP ASVS V7.3, OWASP Cheat Sheet (Error Handling).

## Deployment and recovery controls

**Required property:** deployment configuration enforces security; recovery does not compromise it.

Verify in repo: TLS termination at reverse proxy, HTTP-to-HTTPS redirect, IP allowlist on admin routes, Redis DB separation (0=broker, 1=cache), secrets set in prod env, backup policy.

Failure modes: no TLS, exposed DB/Redis ports, no IP allowlist, secrets defaulted.

Primary sources: OWASP ASVS V14, CISA Secure by Design.

## Primary sources

| Source | When to use | URL |
|---|---|---|
| OWASP Cheat Sheet Series | Control-specific hardening guidance | https://cheatsheetseries.owasp.org/ |
| OWASP ASVS | Control verification requirements | https://owasp.org/www-project-application-security-verification-standard/ |
| OAuth 2.0 Security BCP | OAuth flow hardening | https://datatracker.ietf.org/doc/rfc9700/ |
| MDN browser security | CSP, HSTS, cookie attributes | https://developer.mozilla.org/en-US/docs/Web/HTTP |
| NIST guidance | Authentication, logging, identity | https://csrc.nist.gov/ |
| Official provider security docs | Stripe, Gmail, Outlook, delay providers | (per provider) |

External standards define expected security properties and hardening considerations. They do not by themselves prove a repository-specific vulnerability. Repo truth is the final authority for repository behaviour.
