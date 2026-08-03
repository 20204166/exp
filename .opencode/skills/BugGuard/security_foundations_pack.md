# Security Foundations Pack

Mandatory for every Mode D run. This pack teaches **reasoning and evidence framing** — it is not a flat link catalogue and not a generic security checklist.

Use this pack to structure the Mode D auditor's initial threat model and to frame what evidence each reviewer needs.

## How to use

Before external research, state the exact question:

```text
Security question:
Repo evidence that triggered it:
Foundations section needed:
How the answer could change the threat model or decision:
```

After consulting a section, record in the Security Review artifact:

```text
Foundations section used:
Why it was relevant:
What security question it informed:
What local repository evidence is still required:
```

Repo truth remains the final authority for repository behaviour. External standards define expected security properties and reasoning structure, not repo-specific proof.

## Protected assets

Identify what the system stores, processes, or transmits that an attacker wants.

- User PII: email, name, address, phone
- Authentication material: passwords (hashed), session tokens, OAuth tokens
- Financial data: Stripe customer IDs, payment method tokens
- Evidence integrity: OCR text, delay evidence, claim packs, PDF artifacts
- File uploads: ticket images, PDFs, attachments
- Provider payloads: Gmail/Outlook API responses, delay-provider data
- Admin data: user accounts, enterprise billing, audit logs
- Secrets: SECRET_KEY, ENCRYPTION_KEY, Stripe webhook secret, OAuth client secrets

For each asset, record: where it lives, who can access it, what protects it, what happens if it leaks.

Primary sources: OWASP ASVS V1 (threat modelling and asset inventory), NIST SSDF PO.1 (protect assets).

## Threat actors and attacker capability

Model who can attack the system and what they can do.

- **Unauthenticated external user** — can reach public routes, submit forms, attempt CSRF
- **Authenticated regular user** — has a session, can access own data, may attempt BOLA/IDOR
- **Authenticated user of a different tenant** — cross-tenant access attempts
- **Enterprise admin** — elevated privileges within an enterprise scope
- **System admin** — full admin panel access
- **Insider with DB access** — can read/modify data directly
- **Attacker with stolen session token** — session fixation/hijacking
- **Attacker with OAuth token** — token replay
- **Attacker controlling a webhook endpoint** — replay/forgery
- **Attacker controlling a delay-provider response** — evidence manipulation

For each actor, record: preconditions, reachable entry points, what they can read, what they can modify, what they cannot reach.

Primary sources: OWASP ASVS V1.1, NIST SSDF PO.1, CISA Secure by Design (threat-informed defence).

## Entry points

Identify every external input channel.

- HTTP routes (public, auth-required, admin-gated)
- API endpoints (JSON, form-encoded, multipart upload)
- OAuth callback endpoints
- Webhook endpoints (Stripe, provider)
- Background job triggers (Celery tasks, Beat schedule)
- Email ingestion (Gmail/Outlook scan)
- File uploads (ticket images, CSV, PDF)
- Template rendering (Jinja2 autoescape boundary)
- Static file serving
- Database (direct access in dev/test)
- Environment variables and settings

For each entry point, record: who can reach it, what input format it accepts, what validation exists, what downstream code it invokes.

Primary sources: OWASP WSTG (information gathering, configuration management), OWASP API Security Top 10 (API1-2023 Broken Access Control, API8-2023 Security Misconfiguration).

## Trust boundaries

Map where trust changes.

- **Internet → application** — TLS termination, reverse proxy headers
- **Application → database** — ORM boundary, SQL injection surface
- **Application → object storage** — R2/S3 API, presigned URLs
- **Application → external API** — delay providers, Gmail/Outlook, Stripe
- **User session → application** — cookie-based session, CSRF boundary
- **Background worker → application** — Celery task queue, Redis broker
- **Browser automation → operator portal** — the inviolable final-submit boundary
- **Admin route → admin user** — IP allowlist, admin authorization
- **Enterprise scope → regular user** — tenant boundary, membership checks

For each boundary, record: what crosses it, what trust is assumed on each side, what control enforces the boundary, what happens if the boundary is crossed without authorization.

Primary sources: OWASP ASVS V1.4 (trust boundaries), NIST SSDF PO.1.

## Attacker-controlled input

Distinguish trusted input from attacker-controlled input.

- Form fields, query parameters, JSON body fields
- File upload content and filenames
- URL path segments and query strings
- HTTP headers (Referer, User-Agent, custom headers)
- Cookie values
- OAuth callback parameters (state, code, error)
- Webhook payloads (Stripe events, provider callbacks)
- Email content (ingested messages)
- Delay-provider API responses
- Redis cache values (if attacker can influence cache keys)

For each attacker-controlled input, record: where it enters, what validation exists, where it is used downstream, what encoding/escaping protects each sink.

Primary sources: OWASP Top 10 A03 (Injection), OWASP Cheat Sheet (Input Validation), OWASP API Security Top 10 (API3-2023 Broken Object Property Level Authorization).

## Authentication

Reason about authentication as a security property.

- What proves the user is who they claim to be?
- What session/token is issued on success?
- How long does it live?
- Can it be revoked?
- What happens on failed login (timing, error message, rate limit)?
- Is there email enumeration risk?
- Are there password requirements? Is password hashing adequate?
- Is there 2FA? Where is it enforced?
- What happens on OAuth login failure?
- Are OAuth tokens stored encrypted? (Fernet)

Do not treat "auth exists" as "auth is correct." Verify the repo-specific implementation.

Primary sources: OWASP ASVS V2 (authentication), OWASP Top 10 A07 (Identification and Authentication Failures), NIST 800-63B (digital identity guidelines).

## Authorization

Reason about authorization as a property that must hold on every protected resource access.

- Does every route that returns user-specific data check the requesting user owns that data?
- Is there object-level authorization (BOLA/IDOR check) or only authentication?
- Are admin routes gated by an admin check, not just authentication?
- Are enterprise routes scoped to the user's enterprise membership?
- Can a user access another user's claims, trips, or attachments by ID?
- Can a user access another tenant's data?
- Does the authorization check happen before data is returned, not after?
- Is the authorization check on the ORM query (WHERE user_id=) or on the result?

Primary sources: OWASP ASVS V4 (access control), OWASP Top 10 A01 (Broken Access Control), OWASP API Security Top 10 (API1-2023 Broken Access Control).

## Object ownership and BOLA/IDOR

This is the most common API vulnerability. Reason about it explicitly.

- Every object that has an owner: does the access path check ownership?
- Trip → user_id: does every route that fetches a trip filter by the current user?
- Claim → trip → user_id: is the ownership chain traversed?
- Attachment → claim → trip → user_id: is the full chain traversed?
- Enterprise → members: is membership checked before access?
- Download endpoints: is authorization checked before serving the file?
- Can a user guess/enumerate object IDs to access others' data?

Primary sources: OWASP API Security Top 10 (API1-2023), OWASP ASVS V4.2.

## Privilege transitions

Identify where a user's privilege level changes.

- Regular user → enterprise admin (membership elevation)
- Enterprise admin → system admin (scope escalation)
- Unauthenticated → authenticated (login)
- Authenticated → OAuth-connected (token grant)
- Authenticated → admin (admin flag check)
- Background task context (no user session — what identity does it run as?)

For each transition, record: what triggers it, what control prevents unauthorized elevation, what happens on failure.

Primary sources: OWASP ASVS V4.3, NIST 800-162 (ABAC).

## Attack preconditions

For every suspected weakness, state what an attacker needs before exploitation.

- What authentication is required?
- What knowledge (object IDs, internal state) is required?
- What access (network, same tenant, admin) is required?
- What timing or sequencing is required?
- What feature flag must be enabled?
- What deployment configuration must be present?

If preconditions are unrealistic or the attack path is not reachable, the concern is a hardening opportunity, not a vulnerability.

Primary sources: OWASP WSTG (threat assessment), CWE (precondition fields).

## Attack paths and exploitability

Map the full path from entry point to impact.

1. Entry point (route, endpoint, input)
2. Input processing (validation, parsing)
3. Downstream use (query, template, storage, external call)
4. Control encountered (authorization, encoding, rate limit)
5. Control bypass or absence
6. Impact (data disclosure, modification, denial, privilege escalation)

If any step is not reachable in repo code, the path is theoretical. Record what repo evidence proves reachability.

Primary sources: OWASP WSTG (attack vectors), CWE (exploitation fields), MITRE ATT&CK (only for concrete application attack paths).

## Blast radius

If the weakness is exploited, what is the worst outcome?

- Single user's data disclosed
- All users' data disclosed
- Cross-tenant data access
- Privilege escalation to admin
- Evidence integrity compromised
- Financial fraud (Stripe manipulation)
- Auth bypass for all users
- Denial of service
- Secret leakage

Blast radius informs severity, not existence. A narrow blast radius does not disprove a vulnerability; it lowers its severity.

Primary sources: OWASP ASVS V1.2 (impact assessment), NIST SSDF PO.1.

## Fail-open versus fail-closed

Identify every error path and determine whether it fails open (allows access on error) or fails closed (denies access on error).

- Authorization check throws → does the request proceed or stop?
- CSRF validation fails → is the request rejected or allowed through?
- Session decryption fails → is the user logged out or given a new session?
- Webhook signature verification fails → is the webhook rejected or processed?
- OCR parsing fails → is the claim rejected or submitted with bad data?
- External API call fails → is the fallback safe or does it expose data?
- Storage backend fails → is the upload rejected or silently lost?

**Security controls must fail closed.** A control that fails open is itself a vulnerability.

Primary sources: OWASP ASVS V7.3 (error handling), OWASP Cheat Sheet (Error Handling).

## Deployment assumptions

Security properties may depend on deployment configuration that is not in the code.

- TLS termination at reverse proxy — is HTTP-to-HTTPS redirect enforced?
- IP allowlist on admin routes — is it configured in prod?
- Redis authentication — is it enabled in prod?
- Database network exposure — are ports 5432/6379 publicly reachable?
- Environment variables — are secrets set and not defaulted in prod?
- Feature flags — are optional surfaces disabled in prod?
- CORS origins — are they restricted or wildcard?

Record what deployment config each control depends on. A control that exists in code but is not enabled in deployment is a missing control, not a sufficient one.

Primary sources: OWASP ASVS V14 (configuration), CISA Secure by Design (secure defaults).

## Residual risk

After all controls are verified, what risk remains?

- Known gaps acknowledged in architecture docs
- Controls that are compensating but not sufficient alone
- Deployment-dependent controls not yet verified in prod
- Controls that protect against common attacks but not novel ones
- Trade-offs accepted for usability or availability

Residual risk is not a vulnerability. It is an accepted-risk candidate if compensating controls are adequate.

Primary sources: NIST SSDF PO.5 (risk acceptance), OWASP ASVS V1.3.

## Security-versus-availability trade-off

A control that is too strict can cause availability problems.

- Rate limiting that locks out legitimate users
- IP allowlist that blocks valid admins
- CSRF that breaks legitimate cross-origin requests
- Strict input validation that rejects valid user data
- Session timeout that disrupts long workflows

Record the trade-off for each proposed hardening. If the hardening introduces an availability risk, it needs a Mode A patch with regression tests, not just a Mode D posture note.

Primary sources: OWASP ASVS V11 (business logic), CISA Secure by Design (usability).

## Security-versus-usability trade-off

A control that is too complex can cause usability problems.

- 2FA that frustrates users
- CAPTCHA on every form
- Strict password rules that users circumvent
- Session invalidation that loses work

Record the trade-off. The inviolable product rule (no auto-submit, human-in-the-loop) is a usability boundary that security hardening must not cross.

Primary sources: OWASP ASVS V2.5 (authentication usability), NIST 800-63B (usability considerations).

## False-positive control

Mode D must not inflate concerns into vulnerabilities.

- A theoretical attack path with no reachable repo code → hardening opportunity or note
- A control that exists but could be stronger → hardening opportunity
- A control that depends on deployment config → deployment-dependent gap, not a code vulnerability
- A pattern that looks insecure but is handled by another layer → existing sufficient control

Use the per-concern decision enum (§10 of the Mode D plan) to classify honestly.

Primary sources: OWASP WSTG (false positive reduction), NIST SSDF PO.5.

## Secure-by-design principles

Apply these reasoning lenses to every control:

- **Defence in depth** — does a second control exist if the first fails?
- **Least privilege** — does the code use the minimum privilege needed?
- **Secure defaults** — is the default configuration safe without manual hardening?
- **Control dependency** — does the control depend on another control that might not hold?
- **Trust assumptions** — what does the control assume about its environment?
- **Detection and recovery** — if the control fails, is the failure detected and recoverable?
- **Compensating controls** — if the primary control is weak, does another control mitigate?

Primary sources: OWASP ASVS V1, NIST SSDF (secure-by-design), CISA Secure by Design.

## Primary sources

| Source | When to use | URL |
|---|---|---|
| OWASP ASVS | Control verification requirements | https://owasp.org/www-project-application-security-verification-standard/ |
| OWASP Top 10 | Common vulnerability categories | https://owasp.org/www-project-top-ten/ |
| OWASP API Security Top 10 | API-specific vulnerability categories | https://owasp.org/API-Security/editions/2023/en/0x11-t10/ |
| CWE | Weakness classification and preconditions | https://cwe.mitre.org/ |
| NIST SSDF | Secure development lifecycle | https://csrc.nist.gov/Projects/ssdf |
| CISA Secure by Design | Secure defaults and threat-informed defence | https://www.cisa.gov/secure-by-design |

External standards define expected security properties and reasoning structure. They do not by themselves prove a repository-specific vulnerability. Repo truth is the final authority for repository behaviour.
