# Compliance Specialised Reviewers

Read this file before Stage 9 (Specialised review). It defines the six reviewer roles, sequential execution, artifact ownership, no-backfill rule, incomplete-review behaviour, evidence-audit gate, and final rebuttal. The main auditor must not perform specialist work itself or use a generic self-check as a substitute for reviewer-owned sections.

## Why specialised review exists

Compliance findings fail in different ways: the authority may be stale, the law may not apply, the repo may not implement the claimed behaviour, deployment may differ from code, consequences may be overstated, or the evidence chain may not support the confidence stated. Each material finding must therefore be challenged by a reviewer that owns exactly one legal/compliance question.

## Main auditor boundary

The main auditor owns planning, scoping, spark routing, candidate obligation selection, reviewer assignment, evidence synthesis, confidence caps, recommendations, final rebuttal, and the final audit. It never performs reviewer-owned specialist work. It may correct its own sections after reviewer findings, but it must not write, paste, summarise, transcribe, or backfill any reviewer section.

## Sequential execution

Run reviewers in this order. Do not run them in parallel for material findings.

1. Main auditor creates the initial artifact through Stage 8.
2. Reviewer 1 verifies authority and currency.
3. Reviewer 2 verifies applicability using the verified authority record.
4. Reviewer 3 verifies repository compliance evidence using the verified authority and applicability records.
5. Reviewer 4 verifies operational reality using the repo evidence and earlier validated legal frame.
6. Reviewer 5 evaluates enforcement and consequences using the validated authority, applicability, repo, and operational records.
7. Reviewer 6 audits evidence quality across completed reviewer sections.
8. Main auditor reads all completed sections and performs final synthesis.

If Reviewer 1 overturns authority, downstream review must pause and restart from the corrected authority record. If Reviewer 2 overturns applicability or legal framework, repository, operational, and consequence review must pause until the scope is corrected.

## Reviewer 1 — Authority & Currency Reviewer

Purpose: prove the legal authority itself is correct.

Primary pack: `authority_research_pack.md`.

Owns:
- legislation hierarchy;
- primary/secondary legislation classification;
- commencement and commencement orders;
- amendments, repeals, prospective changes, outstanding changes;
- statutory instruments;
- authority weighting;
- guidance status, withdrawal, archival status, and supersession;
- statutory-code status;
- regulator competence as an authority question;
- case-law status where cited for authority;
- legal freshness and review-by dates.

Must not analyse:
- repository implementation;
- deployment configuration;
- consumer harm or commercial impact;
- whether the organisation's facts satisfy applicability conditions, except to identify stated applicability conditions in the source.

Required output:
```text
Sources re-located:
Authority classifications verified/corrected:
Commencement checks:
Amendment/repeal/outstanding-change checks:
Guidance current/superseded/draft/archived checks:
Case-law status checks:
Authority conflicts:
Findings overturned or confidence-capped:
Outcome: complete / incomplete
```

If commencement, amendment status, or source currency cannot be verified, mark the affected finding `Commencement uncertain`, `Authority conflict`, `Superseded material`, `Draft or consultation only`, or `Evidence insufficient` as applicable. A finding cannot receive a strong final status while a decisive authority check is unverified.

## Reviewer 2 — Applicability Reviewer

Purpose: prove the law actually applies.

Primary pack: `jurisdiction_applicability_pack.md`.

Owns:
- jurisdiction and territorial scope;
- devolved/reserved distinctions;
- organisation legal role;
- trader, consumer, controller, processor, employer, operator, platform, or intermediary status;
- affected group;
- B2B/B2C distinction;
- sector applicability;
- regulated-activity perimeter;
- exemptions and thresholds;
- establishment, place of supply, target market, and extraterritorial scope;
- deployment assumptions needed to decide applicability.

Must challenge whether the main auditor chose the correct legal framework.

Must not analyse:
- source currency except as already verified by Reviewer 1;
- implementation sufficiency;
- operational configuration sufficiency;
- enforcement severity.

Required output:
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

If applicability is unresolved, downstream analysis may continue only as bounded evidence mapping. It must not conclude as though the rule applies.

## Reviewer 3 — Repository Compliance Reviewer

Purpose: challenge implementation assumptions from repository truth.

Primary pack: `repository_mapping_pack.md`.

Owns:
- code paths;
- templates and UI wording in repo;
- email templates;
- compliance documents and internal policy text;
- migrations and data models;
- tests and fixtures;
- feature flags and configuration keys as represented in repo;
- repository evidence status and contradictions.

Must determine whether the repository actually implements, documents, or tests the claimed behaviour.

Must not analyse:
- whether the law applies;
- production/provider configuration not present in repo evidence;
- enforcement severity;
- live operational behaviour.

Required output:
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

If code capability exists but production configuration is unknown, Reviewer 3 must mark the repo capability and hand the deployment question to Reviewer 4. It must not assert deployed compliance.

## Reviewer 4 — Operational Reality Reviewer

Purpose: challenge deployment assumptions.

Primary pack: `operational_verification_pack.md`.

Owns:
- deployed configuration evidence;
- Stripe/customer portal/account configuration where relevant;
- production feature-flag state;
- provider dashboard or account configuration evidence;
- admin tooling and operator workflows;
- customer portal behaviour;
- emails actually sent versus templates;
- scheduled jobs and runtime behaviour;
- logs/audit trails where safely available;
- deployment state and operational procedures.

Must determine whether compliance depends on operational configuration or runtime practice.

Must not analyse:
- legal authority;
- applicability except where an operational fact is missing;
- source interpretation;
- enforcement severity.

Required output:
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

When operational evidence is unavailable, record `Needs operational evidence` or `Deployment dependent`. Do not infer deployment from SDK usage, configuration options, tests, or policy wording.

## Reviewer 5 — Enforcement & Consequence Reviewer

Purpose: evaluate consequences.

Primary pack: `enforcement_pack.md`.

Owns:
- consumer harm;
- likely regulator interest;
- ICO, FCA, CMA, Trading Standards, ASA, ORR, CAA, HMRC, Ofcom, NCSC, Companies House, or other competent-body consequence framing where relevant;
- complaints, chargebacks, civil liability, and remediation urgency;
- severity and likelihood;
- commercial and operational impact;
- high-risk escalation triggers.

Must not reinterpret legislation, reopen authority, or decide applicability. If earlier legal or operational evidence is weak, consequence analysis must say so and cap confidence rather than invent a breach.

Required output:
```text
Harm analysis:
Regulator/enforcement route considered:
Civil/consumer/commercial consequence:
Likelihood and severity:
High-risk escalation triggers:
Evidence dependencies from Reviewers 1-4:
Consequence confidence caps:
Outcome: complete / incomplete
```

Consequence severity cannot convert weak authority, unresolved applicability, or missing deployment evidence into a proven non-compliance finding.

## Reviewer 6 — Compliance Evidence Auditor

Purpose: quality-assure the completed reviewer chain.

Primary inputs: the main auditor's Stage 1-8 sections and Reviewer 1-5 sections.

Reviewer 6 performs no new legal research and no new repository investigation. It checks whether the evidence already recorded supports the conclusions and confidence.

Owns:
- whether Reviewer 1 proved authority and currency;
- whether Reviewer 2 proved applicability;
- whether Reviewer 3 proved repository evidence;
- whether Reviewer 4 proved operational reality;
- whether Reviewer 5 justified consequences;
- contradictions between reviewer outputs;
- missing evidence;
- unsupported assumptions;
- confidence inflation;
- hallucinated reasoning;
- weak source or evidence chains;
- finalisation readiness.

Required output:
```text
Authority proof checked: yes / no / issues
Applicability proof checked: yes / no / issues
Repository evidence checked: yes / no / issues
Operational evidence checked: yes / no / issues
Consequence reasoning checked: yes / no / issues
Contradictions found:
Unsupported assumptions:
Source weaknesses:
Confidence inflation:
Hallucination risks:
Finalisation readiness: pass / pass with caps / incomplete / reject finalisation
Outcome: complete / incomplete
```

Reviewer 6 never cures missing reviewer work. If a required reviewer section is missing or incomplete, Reviewer 6 must mark the affected finalisation path incomplete or confidence-capped.

## No model-name hardcoding

Do not hardcode, assume, or invent model IDs for reviewers. Roles may run as generic subagents or sequential review passes under explicit role reset. If the host supports spawning distinct subagents, prefer distinct subagents. A model mismatch is never a reason to simulate or skip a reviewer.

## Artifact ownership

| Owner | Sections |
|---|---|
| Main auditor | scope; document inventory; claim extraction; initial authority research; requirement mapping; initial findings; final synthesis; final rebuttal; recommendations |
| Reviewer 1 | authority and currency review |
| Reviewer 2 | applicability review |
| Reviewer 3 | repository compliance review |
| Reviewer 4 | operational reality review |
| Reviewer 5 | enforcement and consequence review |
| Reviewer 6 | compliance evidence audit |

## No-backfill rule

No reviewer section may be written, pasted, transcribed, summarised, or backfilled by the main auditor. If a reviewer cannot run independently, mark that reviewer section `Review incomplete: <reason>`. A missing reviewer section is not complete merely because the main auditor believes it could answer the question.

## Incomplete-review behaviour

If a reviewer cannot write independently or required evidence is unavailable:

- mark that reviewer section `Review incomplete: <reason>`;
- record the confidence impact;
- do not finalise the affected finding as strong/conclusive;
- use the bounded status that matches the gap, such as `Evidence insufficient`, `Needs repository evidence`, `Needs operational evidence`, `Deployment dependent`, `Jurisdiction uncertain`, `Authority conflict`, `Commencement uncertain`, or `Qualified legal review required`;
- do not silently treat an incomplete review as a passed review.

## Final rebuttal

The main auditor reads all completed reviewer sections after Reviewer 6 completes or is marked incomplete. It records responses, revises findings, caps confidence, and resolves or escalates contradictions. Where a reviewer overturns a finding, the main auditor revises the status and records the reason. Where the main auditor maintains a finding despite a reviewer challenge, it records the rebuttal and surviving confidence.

Strong final statuses require the decisive specialist reviews plus Reviewer 6 to be complete. If Reviewer 6 rejects finalisation, the main auditor must either rerun the deficient specialist review or issue only a bounded incomplete/evidence-gap status.

## Edge cases

- If Reviewer 1 finds the cited law unverified, repealed, uncommenced, superseded, or conflict-bound, downstream reviewers must not assume the original authority.
- If Reviewer 2 finds the wrong legal framework, Reviewer 3-5 work must be rerun or bounded to the corrected framework.
- If Reviewer 3 finds repo capability but Reviewer 4 lacks deployment proof, the finding is `Deployment dependent` or `Needs operational evidence`, not compliant.
- If Reviewer 4 cannot access production/provider evidence, record the limitation; do not infer from SDK usage.
- If Reviewer 5 identifies serious harm but earlier legal proof is weak, escalate risk without converting the issue into a proven breach.
- If reviewers disagree, record the contradiction and apply the weakest decisive confidence dimension. Do not average conclusions.

## High-risk escalation gate

Apply the gate from `SKILL.md`. If any reviewer reveals a high-risk matter, the main auditor must escalate regardless of initial confidence. The skill may identify and evidence the issue; it must not make the final professional decision or impersonate a solicitor.
