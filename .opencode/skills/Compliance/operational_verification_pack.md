# Operational Verification Pack

Primary reviewer: Reviewer 4 — Operational Reality Reviewer.

Use this pack to determine whether compliance depends on deployment configuration, provider/account settings, runtime behaviour, admin practice, or operator workflows that the repository alone cannot prove.

## Owned question

```text
Does available operational evidence prove the deployed/runtime behaviour needed for the compliance conclusion, or is the conclusion deployment dependent?
```

## Hard boundary

Reviewer 4 must not reinterpret law, reopen authority, decide legal applicability except to identify missing operational facts, or assess enforcement severity. It verifies operational reality or records that operational evidence is unavailable.

## Operational evidence ladder

Classify each operational control at the highest evidenced level only:

- `only documentation claims compliance` — policy/runbook asserts behaviour, no implementation or deployment proof.
- `code supports compliant configuration` — repo capability exists, deployment unknown.
- `default configuration appears compliant` — repo defaults appear aligned, production may override.
- `deployed configuration evidenced` — production/staging deployment evidence shows relevant configuration.
- `operational procedure documented` — runbook/process exists for humans/operators.
- `procedure followed` — ticket, audit trail, log, or other evidence shows process execution.
- `runtime behaviour confirmed` — safe runtime evidence confirms behaviour on the relevant date/environment.

Do not claim a higher level from lower-level evidence.

## Surfaces to verify

Where relevant, check or record unavailable evidence for:

- Stripe account settings, webhooks, customer portal, billing/refund flows, payment-method settings;
- provider dashboard settings, data-location settings, subprocessors, contract/terms version;
- production feature-flag state;
- deployment configuration and environment-specific settings, without printing values;
- admin tooling permissions and actual operator workflows;
- customer portal behaviour and user-visible messages;
- emails actually sent, suppression, deliverability, and template-version evidence;
- scheduled jobs, queue workers, cron/Celery beat state, and execution logs;
- retention/deletion execution on relevant data;
- logging pipelines, redaction in deployed log streams, and retention;
- incident, complaint, DSAR, refund, chargeback, and escalation processes;
- audit logs or immutable records proving actions occurred.

## Safety limits

- Do not call live production services unless explicitly authorised and safe.
- Do not print secrets, env values, API keys, cookies, OAuth material, raw provider payloads, raw user data, DB rows, private URLs, or full raw logs.
- Do not change provider settings, feature flags, production data, account configuration, emails, customer portal settings, or admin state.
- If evidence requires privileged access not available in the repo, record the exact missing evidence.

## Provider dependence

Record:

```text
Provider:
Service:
Relevant configuration:
Evidence source:
Contract/terms version:
Data location/subprocessor evidence:
SDK/code evidence only: yes / no
Operational account evidence available: yes / no
Missing evidence:
```

SDK usage proves an integration surface exists. It does not prove provider compliance, contract version, account configuration, data location, or production webhook state.

## Operational statuses

Use these where operational proof is decisive:

- `Deployment dependent` — compliance turns on deployment/account/runtime configuration.
- `Needs operational evidence` — the required operational proof is unavailable.
- `Evidence insufficient` — available operational evidence is too weak for the claimed status.
- `Operational evidence supports requirement` — bounded to the reviewed environment/date only.

## Reviewer 4 output

```text
Operational surfaces checked:
Deployment/config evidence available:
Provider/account configuration evidence:
Admin/operator workflow evidence:
Runtime/scheduled-job evidence:
Operational evidence unavailable from repo:
Deployment-dependent findings:
Findings overturned or confidence-capped:
Outcome: complete / incomplete
```
