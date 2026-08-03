# Jurisdiction Applicability Pack

Primary reviewer: Reviewer 2 — Applicability Reviewer.

Use this pack to prove whether the verified authority applies to the organisation, activity, people, place, period, and legal role under audit. Do not use it to prove repository implementation or enforcement severity.

## Owned question

```text
Does the verified legal/regulatory framework apply to this organisation, activity, jurisdiction, affected group, and relevant date?
```

## Hard boundary

Reviewer 2 may challenge the legal framework selected by the main auditor. It must not re-perform authority currency work already owned by Reviewer 1 except to record applicability conditions stated by the verified authority. It must not decide implementation sufficiency, operational compliance, or consequence severity.

## UK jurisdiction distinctions

Never assume UK law is uniform. Determine the applicable jurisdiction per requirement:

- United Kingdom-wide;
- Great Britain;
- England and Wales;
- Scotland;
- Northern Ireland;
- Wales-only, Scotland-only, Northern Ireland-only, or England-only application within wider extent;
- overseas territories or Crown dependencies only if actually relevant.

Check territorial extent and territorial application per provision where the authority uses them differently. Do not silently apply England-and-Wales guidance to Scotland or Northern Ireland.

## Devolved and reserved scope

Record whether the subject matter is reserved or devolved where this changes the applicable law or regulator. Where competence differs across UK nations, record each position and the facts needed to select one.

## Legal role

Determine the organisation's role for each requirement, with evidence:

- controller, processor, joint controller;
- trader, consumer-facing trader, marketplace, platform, intermediary;
- employer, worker-facing organisation, recruiter;
- operator, transport provider, ticketing/refund intermediary;
- payment merchant, payment facilitator, agent, introducer, or out-of-scope customer of a payment provider;
- public authority or private body;
- service provider or goods supplier;
- other role required by the authority.

Do not assume role from policy wording alone. Use repo documents, product description, contractual flow, user journey, and operational facts where available. If role cannot be proved, mark applicability unresolved.

## Affected group

Identify who the rule protects or regulates:

- consumer, passenger, customer, business customer;
- data subject, child, vulnerable person;
- employee, worker, contractor, applicant;
- advertiser, subscriber, complainant;
- taxpayer, company officer, regulated person;
- other group.

Record B2B/B2C status explicitly. A consumer rule may not apply to a business user; a child or special-category data context may trigger additional duties.

## Territorial and market facts

Record, where relevant:

- organisation location and establishment;
- place of supply;
- user/data-subject/passenger location;
- target market and marketing audience;
- currency, language, country selector, terms jurisdiction, and delivery geography;
- cross-border processing or service provision;
- whether the relevant event is historic, current, or planned.

If deployment facts determine territorial scope, mark the missing fact and hand deployment proof to Reviewer 4.

## Thresholds and exemptions

For each threshold or exemption:

```text
Threshold/exemption source:
Threshold value or condition:
Organisation measured value:
Evidence for measured value:
Applicability effect:
Missing facts:
```

Examples include turnover, staff count, data-subject volume, passenger volume, transaction value, activity frequency, regulated-service perimeter, small-business exceptions, household/personal-use exemptions, and sector-specific exemptions.

## Applicability statuses

Use exactly one per requirement:

- `applies` — evidence shows the rule governs this organisation, activity, jurisdiction, affected group, and period.
- `likely applies` — strong evidence but one non-decisive fact remains to be confirmed.
- `may apply` — material facts are unresolved; do not conclude as though it applies.
- `does not appear to apply` — evidence suggests non-applicability; record why and the risk if wrong.
- `unresolved` — applicability cannot be determined from available evidence.

Use final finding statuses such as `Jurisdiction uncertain`, `Legal interpretation required`, or `Evidence insufficient` where the applicability issue affects finalisation.

## Regulator remit

If a regulator is relied on, record:

```text
Regulator:
Remit source:
Relevant function:
Organisation/activity/affected group within remit: yes / likely / may / no / unresolved
Evidence:
Regulator considered but not applicable:
```

A regulator discussing a topic is not proof it is competent for this organisation or activity.

## Reviewer 2 output

```text
Legal framework challenged:
Jurisdiction checks:
Territorial scope checks:
Organisation role checks:
Affected group and B2B/B2C checks:
Threshold/exemption checks:
Regulated-activity checks:
Applicability status changes:
Missing facts:
Findings overturned or confidence-capped:
Outcome: complete / incomplete
```
