# Repository Evidence Mapping

Read this file during Stage 7 (repository evidence mapping) and Stage 8 (gap analysis). It explains how to map external requirements and internal claims to actual repository evidence without assuming implementation. A legal source cannot prove the application complies; a repo test cannot prove what the law requires; a compliance conclusion requires both external authority and repository evidence.

## Repo truth and legal authority have different roles

- Legal authority determines the external obligation or recognised interpretation.
- Repository truth determines what the repository currently documents and implements.
- Neither substitutes for the other.
- An internal compliance document is not proof of the law.
- A repo test is not proof that the implementation operates in production as designed.

## Evidence surfaces

Map each requirement and each extracted claim to actual repo evidence across these surfaces:

- compliance document wording (path, heading, exact quote);
- route/API behaviour (registration, method, handler, status codes, schema);
- UI wording (template, partial, visible text, consent flows);
- forms and consent (fields, consent capture, versioning of accepted text);
- configuration (settings, env keys where referenced — never print values);
- database fields (models, migrations, columns, retention columns);
- retention jobs (Celery tasks/background jobs, schedules, deletion paths);
- logging (log events, redaction, retention of logs);
- user-rights workflows (DSAR/deletion/objection/portability paths);
- access control (auth, roles, admin guards, CSRF/CORS/session boundaries);
- emails (templates, sent evidence, suppression);
- exports (data export paths, format, scope);
- provider integrations (Stripe, R2/S3, OAuth, email, delay providers, subprocessor configuration);
- operational procedures (runbooks, handover docs, ops checklists);
- tests (unit/integration/regression);
- audit evidence (AuditLog entries, audit trails in code).

## Do not infer implementation from document wording

A compliance document saying "we encrypt personal data" is a claim, not implementation proof. Locate the actual code/config that performs encryption. If only the document exists, the status is `Document-only alignment` and the implementation evidence is `missing implementation evidence`, not `evidenced alignment`.

Read the actual implementation in the current session. Treat grep hits as leads, not proof. Treat docs and plans as context, not implementation proof. Where the repo's own compliance README states a requirement is not implemented until reflected in code/migrations/tests, honour that rule.

## Environment-dependent compliance

Distinguish code capability from actual deployment configuration. Use the six-level evidence ladder below for each environment-dependent requirement. Compliance claims must be supported by the highest evidenced level; a lower level cannot support a higher claim.

- **code supports a compliant configuration** — the code can be configured to comply, but there is no evidence it is;
- **default configuration is compliant** — the code's default is compliant, but production may override the default;
- **deployed configuration is compliant** — the production deployment configuration is evidenced as compliant (deployment evidence required, not code alone);
- **operational procedure is followed** — a documented procedure governs the behaviour, and there is evidence it is followed;
- **evidence confirms the procedure** — logs, audit trails, or operational evidence confirm the procedure actually ran/ran on the relevant date;
- **only documentation claims compliance** — a policy/document asserts compliance with no implementation or deployment evidence.

Examples of the capability/deployment distinction:

- cookie security flags (Secure, HttpOnly, SameSite) — capability vs configured flags in the deployment environment;
- retention schedules — defined schedule vs applied schedule on production data;
- encryption — available feature vs enabled in deployment;
- regional hosting — code is region-agnostic; the deployment region governs data-residency analysis;
- log redaction — redaction code vs redaction actually applied through deployed log levels/pipeline;
- access controls — defined roles vs roles granted in production;
- analytics — analytics integration vs trackers actually emitted;
- consent tooling — consent tooling present vs configured and enforcing on the live site.

Examples where capability does not equal compliance:

- secure cookies exist in code but are disabled in deployment;
- retention job exists but is not scheduled;
- consent flag exists but UI does not collect valid consent;
- redaction helper exists but some log paths bypass it;
- accessibility component exists but content/process remains non-compliant;
- provider supports UK hosting but account configuration is unknown.

Where the implementation is environment-dependent and the deployment configuration evidence is not available from the repo, mark the requirement `Deployment dependent` and record what evidence is missing. Do not assert compliance based on capability alone.

## Third-party provider dependence

Identify provider dependence and record:

- contractual dependency (provider, service);
- controller/processor/subprocessor role of the provider and the allocation between the organisation and the provider;
- provider terms (version, date, and whether the repo has a copy or only an assumption);
- data locations (where the provider processes/stores data; whether UK/EEA/other, and evidence source);
- contract version and change history if available;
- provider configuration that the repo does not capture (data location, subprocessors, API behaviour defaults);
- service availability and resilience (whether availability claims are evidenced or assumed);
- SDK versus operational behaviour (SDK usage proves the integration surface exists; it does not prove the provider's operational behaviour, contractual terms, or regional configuration);
- webhook security (signature verification, replay handling, idempotency, and whether the production endpoint is the verified one);
- payment-service scope (e.g. whether the provider is a payment-services provider within FCA/perimeter scope and what role — processor vs acquirer vs gateway — the organisation relies on);
- evidence unavailable from the repository.

Do not claim provider compliance from vendor marketing or SDK usage alone. SDK presence proves the integration surface exists; it does not prove the provider's contractual, regional, or operational configuration meets the legal requirement. Where provider terms or data-location information changed since a prior audit, record a drift entry (see `compliance_drift.md`).

## Accessibility

Distinguish:

- legal obligation (the applicable equality/disability law in the relevant jurisdiction);
- applicable standard (e.g. a WCAG version/level asserted by law or regulator expectation);
- claimed conformance level (what the repo document claims — e.g. "meets WCAG 2.2 AA");
- automated-test coverage (what automated tests check);
- manual-test requirements (what only manual review can establish);
- content and operational responsibilities (who is responsible for ongoing content conformance).

Automated accessibility tests do not prove full conformance. Record the gap between claimed conformance and evidenced conformance precisely.

## Security and privacy overlap

Do not treat generic security good practice as automatically legally mandatory. A security control is only a compliance requirement where a legal or regulatory rule makes it so. Map the control to the applicable legal or regulatory requirement before making a compliance claim; otherwise record it as recognised good practice, not a legal duty.

## Tests do not prove production behaviour

A passing test proves the tested path behaves as the test asserts, under the test's conditions. It does not by itself prove production deployment, production configuration, or absence of other paths. Record tests as evidence with their scope, and do not overstate them. A test absence is also not proof of non-compliance; it is an evidence gap.

## No evidence of breach is not proof of compliance either

Symmetric discipline: a missing test, missing policy citation, or theoretical risk is not proof of legal non-compliance (use a bounded evidence-gap status); and a passing test or present policy is not proof of legal compliance (it is evidence within scope). A compliance conclusion requires both external authority and repo evidence, bounded to the reviewed scope and date.