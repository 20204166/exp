# Repository Mapping Pack

Primary reviewer: Reviewer 3 — Repository Compliance Reviewer.

Use this pack to prove what the repository actually documents, implements, tests, or leaves unproved. It cannot prove what the law requires and it cannot prove production deployment state by itself.

## Owned question

```text
Does current repository evidence support the claimed document wording, implementation behaviour, and test coverage for the verified requirement?
```

## Hard boundary

Reviewer 3 must not decide legal authority, applicability, operational deployment state, provider dashboard configuration, live runtime behaviour, or enforcement severity. It records repository evidence and hands operational uncertainty to Reviewer 4.

## Repo truth principles

- Legal authority determines obligations; repo truth determines what is documented and implemented.
- An internal compliance document is not proof of law.
- A law or regulator source is not proof the app complies.
- A grep hit is a lead, not proof.
- A test proves only the tested path under test conditions.
- A missing test is an evidence gap, not proof of breach.
- Docs and plans are evidence only for documentation/planning claims unless tied to implementation.
- Current repo truth beats memory and stale audit notes.

## Evidence surfaces

Check only surfaces relevant to the scoped requirement:

- compliance document wording;
- terms, policies, help text, disclaimers;
- routes, APIs, handlers, schemas, status codes;
- UI templates, visible copy, forms, consent flows;
- email templates and notification code;
- settings and configuration keys, without printing values;
- feature-flag definitions and defaults in repo;
- database models, migrations, columns, constraints;
- retention/background jobs and schedules represented in repo;
- logging, redaction, audit-log code;
- user-rights workflows and exports;
- access control and admin guards;
- provider integration code and webhook handling;
- tests, fixtures, mocks, and assertions;
- operational runbooks stored in repo.

## Evidence record

For each item:

```text
Requirement / Claim ID:
Evidence surface:
Repo path:
Exact evidence:
Read in this session: yes / no
Evidence status: supports / contradicts / partial / missing / lead only
Capability vs deployment: repo capability / default / deployment unknown / not applicable
Limitations:
```

Do not print secrets, env values, tokens, cookies, provider payloads, private URLs, raw user data, or full raw logs.

## Contradictions to search

Record contradictions rather than selecting the convenient source:

- document vs document;
- policy vs terms;
- privacy notice vs logging;
- retention policy vs deletion jobs;
- UI wording vs terms;
- marketing wording vs legal terms;
- API behaviour vs policy;
- code vs configuration defaults;
- tests vs production assumptions;
- current document vs historical document;
- internal commitment vs statutory minimum.

## Capability handoff to Reviewer 4

If repo evidence shows only that the code can be configured compliantly, record that as repo capability. Do not assert production compliance. Hand off to Reviewer 4 for:

- deployed feature-flag state;
- production env/config values;
- provider dashboard/account settings;
- scheduled-job execution;
- emails actually sent;
- admin/operator workflow evidence;
- live customer portal behaviour;
- audit logs proving operational execution.

## Reviewer 3 output

```text
Documents re-read:
Implementation surfaces checked:
Tests checked and limitation stated:
Feature flags/config keys checked without secret values:
Policy-vs-code contradictions:
Repository evidence gaps:
Findings overturned or confidence-capped:
Outcome: complete / incomplete
```
