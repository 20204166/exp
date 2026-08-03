# Compliance Spark Discovery and Routing

Read this file before Stage 1 (Intake and scope). It defines two pre-research scoping activities: (a) compliance spark discovery — identifying and scoring narrow compliance leads before broad research, and (b) legal-domain and regulator routing — identifying the likely legal domain(s) and proving regulator applicability before searching broadly. Both prevent unbounded research and reduce legal hallucination risk.

## Compliance sparks

A compliance spark is a narrow lead that something may warrant a compliance question. A spark is not a breach, not a finding, and not a legal conclusion. Do not let a spark become a legal conclusion without authority, applicability, temporal, and repository evidence.

### Spark examples

- legal citation appears stale;
- policy references a withdrawn regulator page;
- implementation and policy wording differ;
- retention period appears unsupported;
- regulator named without proven remit;
- consumer wording appears broader or narrower than authority;
- jurisdiction is unspecified;
- commencement date is absent;
- draft law is presented as current law;
- internal policy promises more than the identified legal minimum;
- code capability exists but deployment evidence is missing;
- policy claims technical behaviour that tests do not prove;
- different compliance documents conflict;
- official guidance changed after the document review date.

### Spark score

Score each lead 0–4. The score gates the next step, not the conclusion:

| Score | Meaning | Next step |
|---|---|---|
| 0 | noise | discard; do not record |
| 1 | note only | log in spark register; do not research |
| 2 | investigate | record; light research; do not form a finding |
| 3 | form a compliance question | convert to a Stage 4 legal question |
| 4 | create a formal audit finding candidate | carry into Stage 5 authority research and full opposition |

A spark at 3 or 4 becomes a claim/question and enters the staged audit. A spark at 2 stays a logged lead. A spark never carries a compliance status — it carries only a score and a reason.

### Spark record

```text
Spark ID: SPK-NNN
Source (document/implementation surface/observation):
Spark text (what was observed):
Domain hint:
Regulator hint (if any):
Score: 0 / 1 / 2 / 3 / 4
Reason for score:
Became (Claim ID / Requirement ID / discarded / retained as note):
```

Spark discovery is a scoping filter, not a substitute for authority research. A spark scored 4 still requires verified authority, applicability, temporal, and repository evidence before any finding can be finalised.

## Legal-domain routing

Identify the likely legal domain before searching broadly. Domain narrows the regulators consulted and prevents topic-similarity being mistaken for remit.

### Legal domains

Possible domains include:

- data protection;
- privacy;
- PECR/cookies;
- consumer law;
- subscription and recurring billing;
- payments;
- accessibility/equality;
- advertising;
- rail/transport;
- employment;
- taxation;
- company disclosures;
- security obligations;
- records and retention;
- automated decision-making;
- unknown/mixed.

### Domain routing record

For every audit, record:

```text
Primary legal domain:
Secondary legal domains:
Primary regulator:
Secondary regulator:
Possible regulator:
Regulator considered but not applicable:
Evidence for regulator remit:
Unresolved routing questions:
```

## Regulator routing

Do not infer regulator applicability from topic similarity alone. A regulator discussing a topic does not make it the competent regulator for this organisation, activity, and affected group. Prove remit and applicability before treating a regulator source as authority.

For each regulator considered, record:

```text
Regulator:
Remit source (enabling legislation/instrument):
Organisation/activity/affected group within remit: yes / likely / may / no / unresolved
Evidence:
Applicability status: applies / likely applies / may apply / does not appear to apply / unresolved
```

Where a regulator is considered but not applicable, record why (out of remit, wrong sector, wrong affected group, threshold not met). A regulator considered-but-not-applicable is still recorded so future drift can catch a change in remit or activity.

### Routing and the staged audit

Routing output feeds Stage 1 (the scope names the domains and regulators) and Stage 4 (each legal question inherits the domain and regulator). If routing is unresolved, do not continue as though the regulator applies; mark the affected questions `Applicability unresolved` or `Regulator remit unresolved`.
