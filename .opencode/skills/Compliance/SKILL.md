---
name: Compliance
description: Use this skill for any UK-law or regulatory compliance research, document audit, policy-vs-implementation evidence review, legal-authority verification, jurisdiction/applicability analysis, or dated-regulatory-currency check of repository compliance documents and implementation surfaces. It audits repo documents/policies/product behaviour/user-facing wording/operational procedures/implementation evidence against current applicable UK law and authoritative regulatory guidance — conservatively, traceably, jurisdiction-aware, date-aware, and resistant to legal hallucination. Do NOT use for code-correctness bugs (BugGuard), rendered-UI quality (UI), LR drift (audit-lr-drift), or repo-context hygiene (repo-context-curator). This skill supports compliance research and evidence review; it does not replace review by a qualified lawyer where legal interpretation, material exposure, enforcement risk, litigation risk, or unresolved ambiguity exists.
---

# Compliance

## Purpose

Audit repository compliance documents, policies, product behaviour, user-facing wording, operational procedures, and implementation evidence against current applicable UK law and authoritative regulatory guidance. The audit is conservative, traceable, jurisdiction-aware, date-aware, and resistant to legal hallucination.

This skill supports compliance research and evidence review. It does not provide legal advice and does not replace review by a qualified lawyer where legal interpretation, material exposure, enforcement risk, litigation risk, or unresolved ambiguity exists.

Creating this skill does not establish that the repository or organisation is legally compliant.

## When to use

Use whenever an agent must: audit repo compliance/privacy/cookie/retention/accessibility/terms/refund/consumer/data-processing/security/operational documents or policies; verify a legal or regulatory citation; check effective dates, commencement, amendments, superseded guidance, or draft vs current law; compare repo implementation evidence against a repo compliance document and against applicable UK legal/regulatory requirements; identify incorrect/outdated legal claims, overstated or understated wording, implementation-policy mismatches, jurisdiction mistakes, effective-date mistakes, deployment-dependent uncertainty, or internal commitments stricter than the law; produce a traceable compliance audit artifact.

Do not conduct a broad "all laws" audit. Require an explicit scope before proceeding.

## Do not use for

- Code-correctness or security bugs → BugGuard.
- Rendered-UI quality / accessibility conformance testing / visual polish → UI.
- LR drift / surface drift audit → audit-lr-drift.
- Repo context hygiene / persona maintenance → repo-context-curator.

When a Compliance finding implies a code, config, test, migration, or runtime change, record a `Recommended implementation follow-up` in the audit artifact only. Do not edit application code, tests, configuration, migrations, dependencies, generated files, or production policies. A future application or policy edit must be a separately approved task with its own regression and legal-review controls.

## Hard boundaries (non-negotiable)

- Never invent legislation, regulations, statutory instruments, sections, commencement dates, regulator powers, duties, exemptions, deadlines, thresholds, territorial extent, case names, judgments, enforcement decisions, regulator guidance, or legal quotations.
- If a source cannot be located and verified, record it as `unverified`. Do not reconstruct likely statutory wording from memory.
- Never cite a search-result snippet or AI summary as legal authority.
- Never treat an internal repo compliance document as proof of the law.
- Enactment does not mean commenced; publication does not mean legal effect; consultation does not mean current law; archived guidance is not current guidance; revised legislation is not complete without checking outstanding changes; the latest page did not necessarily govern an earlier event.
- Do not assume "UK law" is one uniform set of rules. Determine jurisdiction and applicability per audit. If applicability is unresolved, do not continue as though the rule applies.
- Do not output "fully compliant", "legally compliant", "this guarantees compliance", "no legal risk", or "the law definitely requires this" unless the evidence threshold expressly permits the statement and all material uncertainty is resolved.
- A "no source found" result is not proof: no relevant case found is not proof no case exists; a missing regulator page is not proof no duty exists. Record database and search limitations.
- Do not impersonate a solicitor or make the final professional decision on any high-risk matter (see Escalation).
- Do not average conflicting official sources. Rank by authority, check dates and scope, record the conflict, and escalate unresolved interpretation.
- A missing test, missing policy citation, or theoretical risk is not proof of legal non-compliance. Use a bounded evidence-gap status.

## What this skill cannot do

This skill cannot establish that the repository or organisation is legally compliant. It cannot give legal advice. It cannot waive the need for qualified legal review on high-risk matters. It cannot prove a negative (no relevant law, no relevant case). It cannot convert an internal policy into law. It cannot convert a consultation or draft into a current duty.

## Authority classification

Every external source must be classified; do not collapse categories into "official source". Full hierarchy and discovery for new audits lives in `authority_research_pack.md`. Summary:

- Mandatory legal source classification: primary legislation; secondary legislation/SI; retained/assimilated/continuing EU-derived law; binding court/tribunal decision; statutory code of practice; regulator rule; regulator decision/enforcement notice; regulator guidance; official government guidance; official consultation/draft; official standard; industry code; vendor documentation; secondary commentary; community material; unknown authority.
- Default tier order (contextual, not mechanically numerical): Tier 1 primary legal authority (legislation.gov.uk, enacted/revised legislation, commencement, SI, schedules, territorial-extent, explanatory notes only as explanation, binding court/tribunal judgments, statutory codes, binding regulator rules) → Tier 2 authoritative regulator material (ICO, CMA, FCA, ORR, DfT, EHRC, CAA, ASA, Ofcom, HMRC, NCSC, Companies House, other competent UK regulators) → Tier 3 official GOV.UK guidance → Tier 4 official standards and authoritative technical guidance (W3C/WCAG, BSI/ISO, NCSC, OWASP) → Tier 5 official implementation documentation → Tier 6 secondary material.
- Prove the regulator's remit and the organisation/activity's applicability before applying a regulator source.
- Identify standards as: legally incorporated; regulator-expected; recognised good practice; or voluntary technical guidance.

## Mandatory official research sources

Use and record: legislation.gov.uk; GOV.UK; relevant regulator websites; Find Case Law from The National Archives; UK Supreme Court judgments; official tribunal/regulator decision databases; official statutory-code repositories; official consultation and policy-paper collections; official archived material where current pages refer to superseded guidance.

Case-law research records: court; jurisdiction; neutral citation; judgment date; precedential relevance; binding/persuasive/distinguishable/overturned/appealed/uncertain status where verifiable; database coverage limitations; whether qualified legal research is needed. Case-law research is not mandatory for every routine requirement; use it when statutory meaning, interpretation, precedent, enforcement history, or disputed applicability depends on it. Absence of a judgment from one database does not prove no relevant case exists.

Every source record (see `source_record_template.md`) must include: Source date; Effective date; Research/access date; Version/status; Temporal applicability; Outstanding-change check; Superseded-material check.

## Jurisdiction and applicability

Every audit must determine, where relevant: UK-wide vs England and Wales vs Scotland vs Northern Ireland vs Great Britain; devolved vs reserved; overseas territories/Crown dependencies if actually relevant; organisation location; user/data-subject location; place of establishment; place of supply; target market; regulated activity; public vs private sector; controller/processor/employer/trader/platform/intermediary/operator role; B2B vs B2C; affected group; sector regulator; territorial/extraterritorial scope; exemptions; thresholds; special categories; contractual commitments beyond statutory minimums.

Record an `Applicability status` per requirement: applies / likely applies / may apply / does not appear to apply / unresolved — with the evidence supporting that classification. If unresolved, do not continue as though the rule applies. Full model in `jurisdiction_applicability_pack.md`.

## Temporal validity

Every legal or regulatory conclusion must be date-aware. Check, where relevant: date made/enacted; Royal Assent; commencement date and any commencement orders; staged/territorial commencement; amendments; repeals; prospective amendments; outstanding changes; transitional, savings, and sunset provisions; temporary measures; effective/revision/withdrawal dates of guidance; superseded versions; consultation and draft vs final status; enforcement grace periods. Compare the law at the document's issue date, the current law, and the planned operational date. Authority/currency checks are owned by Reviewer 1 using `authority_research_pack.md`; applicability date facts are owned by Reviewer 2 using `jurisdiction_applicability_pack.md`.

## Workflow

Perform the staged audit in `compliance_document_audit.md`:

0. Spark discovery and routing (score compliance leads 0–4; route legal domain and prove regulator remit before broad research).
1. Intake and scope (explicit scope required; no broad "all laws" audit).
2. Document inventory (detect contradictions across the 14 pair-types; do not silently choose one).
3. Atomic claim extraction (each claim receives a stable ID; not paragraph-summary level).
4. Legal-question formulation per material claim.
5. Authority research (locate and verify authoritative sources; short exact quotations only; declare proposition type).
6. Requirement normalisation (translate authority into evidence-backed requirements without overstating).
7. Repository evidence mapping (read actual implementation; do not infer from document wording; use the 6-level evidence ladder).
8. Gap analysis (separate finding types; classify each requirement; do not call a gap a legal breach without sufficient evidence).
9. Specialised review (every material finding challenged sequentially by specialist reviewers before finalisation — see below; includes an authority/currency hard gate and final evidence-audit gate).
10. Final synthesis (bounded conclusion only after opposition; decompose confidence; state scope integrity).

A separate drift re-audit mode re-checks prior audits against current law/guidance/implementation/deployment/provider (`compliance_drift.md`).

## Repository evidence mapping

Map each requirement and claim to actual repo evidence: compliance document wording; route/API behaviour; UI wording; forms and consent; configuration; database fields; retention jobs; logging; user-rights workflows; access control; emails; exports; provider integrations; operational procedures; tests; audit evidence. Do not infer implementation from document wording; read the actual evidence. Full repo model in `repository_mapping_pack.md`; deployment and runtime verification model in `operational_verification_pack.md`.

Environment-dependent controls (cookie flags, retention schedules, encryption, regional hosting, log redaction, access controls, analytics, consent tooling) must distinguish code capability from actual deployment configuration. Third-party provider dependence (contractual role, provider configuration, data location, subprocessors, API behaviour) must not be assumed compliant from SDK usage alone.

Finding types are separated, not merged: every finding distinguishes External legal/regulatory finding; Internal document finding; Implementation finding; and Operational/deployment finding. Each may carry its own status; the overall status is the bound of the four (e.g. legal requirement verified but implementation unknown; internal policy inaccurate but implementation compliant).

Confidence is decomposed into dimensions (Authority / Temporal / Jurisdiction / Applicability / Repository-document / Implementation / Operational-deployment / Overall). Overall confidence must not exceed the weakest decisive dimension without a written reason.

## Specialised reviewer requirement

Every material finding must be challenged through six specialised reviewer roles before finalisation. Each reviewer owns one legal/compliance question. The main auditor must not merely double-check itself and must not perform specialist work itself; general AI output is not a substitute for reviewer-owned artifact sections. Reviewers may run as generic subagents or sequential review passes with explicit role reset; the skill does not require dedicated repository agents. Roles, sequencing, ownership, incomplete-review behaviour, evidence-audit behaviour, and final rebuttal are defined in `compliance_opposition.md`.

- Reviewer 1 — Authority & Currency Reviewer (law exists / citation exact / commenced / amended-repealed / guidance current / authority weighting / regulator competence / case-law status / legal freshness). Primary pack: `authority_research_pack.md`. Never analyses implementation.
- Reviewer 2 — Applicability Reviewer (jurisdiction / territorial scope / legal role / consumer-trader status / exemptions / sector perimeter / B2B-B2C / regulated activity / deployment facts needed for applicability). Primary pack: `jurisdiction_applicability_pack.md`.
- Reviewer 3 — Repository Compliance Reviewer (code / templates / emails / docs / migrations / tests / feature flags / repository evidence). Primary pack: `repository_mapping_pack.md`.
- Reviewer 4 — Operational Reality Reviewer (Stripe/provider configuration / feature flags in deployment / admin tooling / customer portal / emails actually sent / operator workflows / runtime state). Primary pack: `operational_verification_pack.md`.
- Reviewer 5 — Enforcement & Consequence Reviewer (consumer harm / regulator exposure / chargebacks / civil liability / severity / likelihood / commercial impact). Primary pack: `enforcement_pack.md`. Never reinterprets legislation.
- Reviewer 6 — Compliance Evidence Auditor (quality assurance of Reviewers 1-5; contradictions, missing evidence, unsupported assumptions, confidence inflation, hallucinated reasoning, source weaknesses). Performs no new legal research.

Each reviewer writes its own section directly into the audit artifact. The main auditor must not write, paste, transcribe, summarise, or backfill reviewer-owned sections. If a reviewer cannot write independently, mark the review `incomplete`. No reviewer section may be backfilled by the main auditor.

Required sequence: main auditor initial artifact → Reviewer 1 authority/currency → Reviewer 2 applicability using verified authority → Reviewer 3 repository compliance using verified authority/applicability → Reviewer 4 operational reality using repo evidence and legal frame → Reviewer 5 enforcement/consequence using validated earlier records → Reviewer 6 evidence audit → main auditor final rebuttal and synthesis.

## Artifact routing

Create one persistent artifact per audit at `docs/compliance/audits/COMP-YYYYMMDD-NNN.md`. If the repository has an existing compliance-audit convention that conflicts, use the repo convention and note the deviation in the artifact. Create the `audits/` directory lazily on the first real audit. Use the full template in `compliance_audit_template.md`. Do not pre-create the directory or any audit file during skill setup.

Ownership: main auditor owns scope, document inventory, claim extraction, initial research, requirement mapping, initial findings, reviewer assignment, final rebuttal, recommendations, and final synthesis. Reviewer 1 owns authority and currency. Reviewer 2 owns applicability. Reviewer 3 owns repository compliance evidence. Reviewer 4 owns operational reality. Reviewer 5 owns enforcement and consequences. Reviewer 6 owns evidence quality audit. No reviewer section may be backfilled by the main auditor.

## High-risk escalation gate

This skill may identify and evidence a high-risk issue but must not make the final professional decision. Require qualified legal review before strong conclusions or implementation where the finding involves any of: criminal liability; regulatory enforcement exposure; significant consumer detriment; discrimination; employment dismissal or worker status; immigration; tax; financial services; payments regulation; health or medical data; children; special-category personal data; automated decision-making with significant effects; cross-border processing; major retention or deletion decisions; litigation or threatened proceedings; uncertain case law; conflicting authorities; material contractual liability; substantial financial exposure; regulator notification; statutory reporting; unclear territorial scope; advice tailored to a specific person's legal position; facts material to the legal question are incomplete; competing legal interpretations exist; a legal role (controller/processor/employer/trader/operator) is disputed; a proposed policy change affects user rights; or historic liability for a past period is being assessed.

The skill provides useful evidence and bounded analysis up to the escalation gate; it does not stop immediately on the first risk indicator — instead, record the risk, mark the finding `Qualified legal review required`, and complete the bounded non-legal-advice portions of the analysis.

## Bounded status vocabulary

Avoid a binary compliant/non-compliant model. Use bounded statuses and define which require escalation:

| Status | Escalate? |
|---|---|
| Evidenced alignment | No |
| Compliant | Only within reviewed scope and only when all decisive reviewer sections are complete |
| Likely compliant | If missing facts are non-decisive and recorded |
| Guidance-aligned | No |
| Partial alignment | If material |
| Likely non-compliant | Yes |
| Non-compliant | Yes; requires verified authority, applicability, repo/operational evidence, and consequence review unless purely internal |
| Document gap | No |
| Implementation evidence gap | If material |
| Needs repository evidence | If material |
| Needs operational evidence | If material |
| Document/implementation mismatch | Yes |
| Outdated legal reference | Yes |
| Inaccurate legal claim | Yes |
| Potential compliance gap | Yes |
| Potential legal breach — qualified review required | Yes |
| Internal commitment stricter than identified legal minimum | No (record; change requires separate approval) |
| Existing control appears sufficient | No |
| Applicability unresolved | Yes |
| Jurisdiction uncertain | Yes |
| Legal interpretation unresolved | Yes |
| Legal interpretation required | Yes |
| Deployment dependent | If material |
| Authority conflict | Yes |
| Commencement uncertain | Yes |
| Evidence insufficient | If material |
| Superseded material | Yes |
| Draft or consultation only | Yes |
| Out of scope | No |
| No material gap identified within reviewed scope | No |
| Needs more evidence | If material |
| Qualified legal review required | Yes |

Forbidden phrases unless the evidence threshold expressly permits and all material uncertainty is resolved: "fully compliant"; "legally compliant"; "this guarantees compliance"; "no legal risk"; "the law definitely requires this".

Prefer bounded wording: "no material gap identified within the reviewed scope"; "aligned with the cited guidance as of the research date"; "implementation evidence supports this requirement"; "applicability remains uncertain"; "legal review required"; "outside reviewed scope"; "deployment-dependent"; "policy commitment exceeds the minimum identified legal requirement".

Use `Compliant` only as a scoped audit status, never as an organisation-wide guarantee. Use `Non-compliant` only when the decisive authority, applicability, repository/operational evidence, and consequence reasoning have survived the specialised reviewer chain. Use evidence-gap statuses rather than breach language where proof is missing.

## Edge cases the skill handles

Conflicting official sources (rank authority, check dates/scope, record conflict, escalate unresolved interpretation); internal policy stricter than law (record statutory minimum vs internal commitment vs contractual expectation; check contractual effect, consumer expectation, fairness, marketing representation, governance approval, reliance, operational feasibility, existing user commitments, and regulator expectations; never recommend weakening merely because law permits less; status: `Internal commitment stricter than identified legal minimum — change requires separate legal, commercial, and governance approval`); law changed after document publication (compare law at issue date vs current vs planned; do not retroactively label a historically accurate document wrong); draft legislation and consultations (label as draft/bill/consultation/proposed code/pending approval/not yet in force; never convert future proposals into current duties); commencement uncertainty (enactment/Royal Assent/making does not prove every provision is in force; require a commencement check); devolved differences (never silently apply England-and-Wales guidance to Scotland or Northern Ireland); regulator guidance vs binding duty (describe whether it interprets law, sets expectations, is a statutory code, is binding, is evidential, or is advisory); missing case law ("no result found" ≠ "no case law exists"; record database and search limitations; a factually distinguishable case is weaker authority for the exact question); archived or removed pages (use official archives; record archived status and verify supersession); conflicting repo documents (do not choose the most convenient; identify ownership, effective dates, audience, hierarchy); environment-dependent compliance (distinguish code capability from actual deployment configuration using the 6-level evidence ladder); third-party provider dependence (do not claim provider compliance from SDK usage or vendor marketing alone; record terms, data location, contract version, webhook security, payment-service scope); accessibility (distinguish legal obligation vs applicable standard vs claimed conformance level vs automated-test coverage vs manual-test requirements vs content/operational responsibilities); security and privacy overlap (do not treat generic security good practice as automatically legally mandatory; map to the applicable requirement before making a compliance claim); no evidence of breach (a missing test, missing policy citation, or theoretical risk is not proof of legal non-compliance; use a bounded evidence-gap status); compliance drift (absence of visible change is not proof no drift occurred; use `compliance_drift.md`).

## Support files

Read each only when the relevant workflow is active:

- `authority_research_pack.md` — Reviewer 1 pack for authority hierarchy, official-source discovery, commencement, amendments, repeals, source currency, authority weighting, case-law status, and source-conflict handling.
- `jurisdiction_applicability_pack.md` — Reviewer 2 pack for UK jurisdiction distinctions, applicability ladder, legal role, exemptions, thresholds, territorial scope, and regulated-activity boundaries.
- `repository_mapping_pack.md` — Reviewer 3 pack for mapping external requirements and internal claims to actual repository evidence without assuming implementation.
- `operational_verification_pack.md` — Reviewer 4 pack for deployment configuration, provider/admin/customer-portal evidence, runtime behaviour, and operational evidence limits.
- `enforcement_pack.md` — Reviewer 5 pack for harm, regulator exposure, likelihood, severity, civil/commercial impact, and escalation framing.
- `uk_legal_authority_pack.md` — legacy reference retained for compatibility; prefer `authority_research_pack.md` for new audits.
- `jurisdiction_and_temporal_pack.md` — legacy reference retained for compatibility; prefer `authority_research_pack.md` plus `jurisdiction_applicability_pack.md` for new audits.
- `compliance_document_audit.md` — full staged audit workflow (Stage 0 spark/routing through Stage 10 final synthesis) with per-stage required fields.
- `repository_evidence_mapping.md` — legacy reference retained for compatibility; prefer `repository_mapping_pack.md` and `operational_verification_pack.md` for new audits.
- `compliance_opposition.md` — six specialised reviewer roles, sequencing, artifact ownership, no-backfill rule, incomplete-review behaviour, evidence-audit gate, final rebuttal.
- `compliance_audit_template.md` — full `COMP-YYYYMMDD-NNN.md` artifact skeleton.
- `source_record_template.md` — reusable per-source record fields.
- `validation_commands.md` — safe documentation-only validation commands discovered from repo truth.
- `compliance_spark_and_routing.md` — spark discovery (0–4 score) and legal-domain/regulator routing before broad research.
- `compliance_drift.md` — compliance-drift workflow for re-checking prior audits against current law/guidance/implementation/deployment/provider.

## Fact taxonomy

Reuse the repo's existing taxonomy where it overlaps (`docs/compliance/00_audit_foundation.md`): Repo-supported fact; External-source fact; Reasoned inference; Unresolved item requiring counsel/product decision. This skill additionally classifies every external source by authority tier and the repo evidence by implementation surface, and never lets one substitute for the other.

## Completion requirement

Once invoked for an audit, complete the full staged workflow. Do not stop mid-stage and declare a result. A reviewer only counts when its findings are durably captured in the artifact under its own heading. Do not mark a finding final without the relevant reviewer passes actually completed (or marked `incomplete`). State which stages were not reached and why if interrupted.

## Anti-hallucination verification

Before claiming what a source says: locate and verify it; record the access date; keep quotations short and exact; do not fabricate quotation marks around paraphrases. Before claiming what the repo implements: read the actual implementation evidence in this session; treat grep hits as leads, not proof. Treat docs and plans as context, not implementation proof unless the claim is explicitly about documentation or planning. Let current repo truth beat old memory; let verified external authority determine external obligation. A legal source cannot prove the application complies; a repo test cannot prove what the law requires; a compliance conclusion requires both external authority and repo evidence.

## Approval gate

End every audit run with the bounded disclaimer:

```text
This audit produced evidence and findings within the reviewed scope only.
It did not establish that the repository or organisation is legally compliant.
It does not replace review by a qualified lawyer where legal interpretation, material exposure, enforcement risk, litigation risk, or unresolved ambiguity exists.
No application code, tests, configuration, migrations, dependencies, generated files, or production policies were changed by this audit.
Any recommended implementation or policy change is a separately approved task with its own regression and legal-review controls.
```
