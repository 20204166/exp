# Compliance Document Audit Workflow

Read this file before running an audit. It defines the full staged workflow. Each stage lists required fields. Every material stage output must be captured in the audit artifact (`compliance_audit_template.md`). Do not skip stages and do not collapse the audit to paragraph-summary level.

The work is chaired by the main auditor, who owns scope, document inventory, claim extraction, initial research, requirement mapping, initial findings, reviewer assignment, final rebuttal, and final synthesis. Reviewers own their own specialist sections (see `compliance_opposition.md`).

## Stage 0 — Spark discovery and routing

Before Stage 1, perform spark discovery and legal-domain/regulator routing (see `compliance_spark_and_routing.md`). Record a spark register and a domain/regulator routing record. Score each lead 0–4; only sparks scored 3–4 enter the staged audit as claims/questions. Sparks do not carry compliance status and cannot become findings without authority, applicability, temporal, and repository evidence. If regulator routing is unresolved, mark affected questions `Applicability unresolved` or `Regulator remit unresolved` and do not continue as though the regulator applies.

## Stage 1 — Intake and scope

Record (do not proceed without an explicit scope; no broad "all laws" audit):

```text
Audit ID:
Audit date:
Target documents:
Target implementation surfaces:
Organisation/activity:
Product/service:
Jurisdiction:
Affected users:
Legal domains:
Regulators:
Relevant operational date:
Out-of-scope areas:
Known assumptions:
```

If a regulator is named, prove its authority/remit and the organisation's applicability (see `authority_research_pack.md` and `jurisdiction_applicability_pack.md`).

## Stage 2 — Document inventory

For every relevant document, record:

```text
path:
title:
owner if known:
purpose:
intended audience:
jurisdiction claimed:
effective date:
review date:
source citations:
linked implementation:
conflicting or duplicate documents:
stale or missing metadata:
```

Detect contradictory documents. Do not silently choose one. Where the repo has an existing precedence framework (e.g. `docs/compliance/README.md`), record it and respect it where compatible; record any deviation.

### Contradiction pairs to search explicitly

The audit must explicitly search for contradictions across:

- document versus document;
- policy versus terms;
- privacy notice versus actual logging;
- retention schedule versus deletion jobs;
- UI wording versus terms;
- marketing wording versus legal terms;
- API behaviour versus policy;
- code versus configuration;
- tests versus production/deployment assumptions;
- current document versus historical version;
- regulator guidance versus legislation;
- lower authority versus higher authority;
- different jurisdictional sources;
- internal commitment versus statutory minimum.

Record each detected contradiction in the conflict register (see `compliance_audit_template.md`) with precedence, evidence, and escalation. Do not silently choose one source.

## Stage 3 — Claim extraction

Extract atomic compliance claims from repo documents. Do not audit a long document only at paragraph-summary level. Each claim must receive a stable identifier.

Examples:
- "We retain records for X years."
- "Users may request deletion."
- "Refunds are issued within X days."
- "Cookies are only used after consent."
- "The service meets WCAG level X."
- "Automated decisions are not used."
- "Personal data is encrypted."
- "The company acts as controller."

Each claim record must include:
```text
Claim ID:
Source document:
Source location (path/heading/line):
Claim text (exact quote or close paraphrase marked as such):
Implied legal proposition:
Implied implementation commitment:
```

## Stage 4 — Legal-question formulation

For each material claim:
```text
Claim ID:
Repository claim:
Legal question:
Jurisdiction:
Applicable role:
Relevant date:
Authority needed:
Implementation evidence needed:
```

Research must answer that specific question. Do not conduct unlimited legal browsing.

## Stage 5 — Authority research

Locate and record authoritative sources (see `authority_research_pack.md`; `uk_legal_authority_pack.md` remains a legacy compatibility reference). For each source, capture (use `source_record_template.md`):

```text
Source ID:
Title:
Publisher/body:
Source type:
Authority tier:
URL:
Jurisdiction:
Citation or reference:
Relevant section/regulation/paragraph:
Publication date:
Effective date:
Access date:
Current/superseded/draft/archived:
Quoted or closely paraphrased proposition:
Exact words verified: yes/no
Applicability conditions:
Known amendments or outstanding changes:
Conflicting authority:
Research limitations:
```

Keep quotations short and exact. Do not fabricate quotation marks around paraphrases. If a source cannot be located and verified, record `unverified` and do not assert the proposition.

## Stage 6 — Requirement normalisation

Translate the authority into an evidence-backed requirement without overstating it. Use:
```text
Requirement ID:
Authority source:
Requirement type:
  - mandatory legal duty
  - conditional legal duty
  - regulator rule
  - statutory-code expectation
  - regulator guidance
  - recognised good practice
  - internal policy commitment
Subject:
Trigger:
Required action:
Deadline/frequency:
Exceptions:
Evidence required:
Uncertainty:
```

Do not convert guidance into a mandatory legal duty. Do not convert a consultation or draft into a current duty. Record an internal policy commitment as a separate requirement type from a legal duty; do not conflate them.

## Stage 7 — Repository evidence mapping

Map each requirement to actual repo evidence (see `repository_mapping_pack.md`; use `operational_verification_pack.md` for deployment/runtime questions):

- compliance document wording;
- route/API behaviour;
- UI wording;
- forms and consent;
- configuration;
- database fields;
- retention jobs;
- logging;
- user-rights workflows;
- access control;
- emails;
- exports;
- provider integrations;
- operational procedures;
- tests;
- audit evidence.

Do not infer implementation from document wording. Read the actual implementation evidence in this session. Treat grep hits as leads, not proof. Treat docs and plans as context, not implementation proof.

## Stage 8 — Gap analysis

Classify each requirement using the bounded status vocabulary (see `SKILL.md`). Use one of:
- compliant
- likely compliant
- evidenced alignment
- partial alignment
- document-only alignment
- implementation-only alignment
- wording inaccurate
- outdated source
- missing implementation evidence
- needs repository evidence
- needs operational evidence
- missing document coverage
- conflicting internal documents
- stricter internal commitment
- potentially non-compliant
- likely non-compliant
- non-compliant
- applicability unresolved
- jurisdiction uncertain
- legal interpretation unresolved
- legal interpretation required
- authority conflict
- commencement uncertain
- deployment dependent
- evidence insufficient
- out of scope

Do not call a gap a legal breach without sufficient evidence. A missing test, missing policy citation, or theoretical risk is not proof of legal non-compliance — use a bounded evidence-gap status (e.g. `Implementation evidence gap`, `Needs repository evidence`, `Needs operational evidence`, `Deployment dependent`, `Evidence insufficient`).

### Finding-type separation

Every finding must clearly distinguish four finding types. Do not merge them into one paragraph or one status:

```text
External legal/regulatory finding:
Internal document finding:
Implementation finding:
Operational/deployment finding:
```

This separation lets a finding conclude, for example: legal requirement verified but implementation unknown; internal policy inaccurate but implementation compliant; implementation inconsistent with internal policy but law unresolved; policy commitment exceeds identified legal minimum; deployment configuration determines compliance; or no legal requirement proven but hardening or policy clarification may still be advisable. Each finding type may carry its own status and confidence dimensions; the overall status is the bound of the four.

## Stage 9 — Specialised review

Every material finding must be challenged before finalisation (see `compliance_opposition.md`). The specialised reviewers run sequentially:

- Reviewer 1 — Authority & Currency.
- Reviewer 2 — Applicability.
- Reviewer 3 — Repository Compliance.
- Reviewer 4 — Operational Reality.
- Reviewer 5 — Enforcement & Consequence.
- Reviewer 6 — Compliance Evidence Audit.

Each reviewer writes its own section directly into the artifact. The main auditor must not write, paste, transcribe, summarise, or backfill reviewer-owned sections. If a reviewer cannot write independently, mark the review `incomplete`. Do not run all reviewers in parallel; each reviewer benefits from validated work produced earlier. If Reviewer 1 or Reviewer 2 overturns the legal frame, downstream reviews must pause and restart or be bounded to the corrected frame.

## Stage 10 — Final synthesis

Only after specialised review may the main auditor issue a bounded conclusion. The main auditor reads all completed sections, performs a final rebuttal, and records the bounded status per finding. Apply the high-risk escalation gate (see `SKILL.md`): escalate any high-risk matter to `Qualified legal review required` and do not make the final professional decision.

The final synthesis must use the bounded status vocabulary, the decomposed confidence dimensions, and the matrix table from `compliance_audit_template.md`. The audit closes with the approval-gate disclaimer from `SKILL.md`.

### Authority/currency and evidence-audit hard gates

Before finalising any material finding, confirm Reviewer 1's authority/currency checks were completed (not merely attempted). If commencement, amendment, repeal, supersession, currentness, or authority weighting is failed or `unverified`, the finding may not be finalised as strong/conclusive; record a bounded status such as `Authority conflict`, `Commencement uncertain`, `Superseded material`, `Draft or consultation only`, `Legal interpretation required`, or `Evidence insufficient`.

Before finalising any material finding, confirm Reviewer 6 completed the evidence audit or explicitly marked the affected path incomplete. If Reviewer 6 identifies missing decisive evidence, contradiction, unsupported assumption, hallucination risk, source weakness, or confidence inflation, the main auditor must cap confidence, rerun the deficient specialist review, or issue only a bounded incomplete/evidence-gap status.

### Confidence decomposition

Replace generic confidence with decomposed dimensions per finding:

```text
Authority confidence:
Temporal confidence:
Jurisdiction confidence:
Applicability confidence:
Repository-document confidence:
Implementation confidence:
Operational/deployment confidence:
Overall confidence:
```

Overall confidence must not exceed the weakest decisive dimension without a written reason. Record the dimension that caps overall confidence.

### Audit scope integrity

Every final conclusion must state explicitly, bounded to this audit (do not turn a narrow audit into a claim about the whole organisation):

```text
Reviewed scope:
Unreviewed scope:
Documents reviewed:
Implementation surfaces reviewed:
Operational evidence reviewed:
Jurisdictions reviewed:
Dates covered:
Limitations:
```

A conclusion about the whole organisation is only permissible where the reviewed scope actually covers it and all reviewer sections are complete.
