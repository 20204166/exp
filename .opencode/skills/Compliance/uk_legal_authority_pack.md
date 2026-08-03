# UK Legal Authority Pack

Read this file during Stage 5 (Authority research) and whenever classifying, citing, or ranking a legal source. This pack defines how to find, classify, and cite authoritative UK legal and regulatory material. It is not a link dump: it teaches the auditor how and when to use each source type and how to record limitations.

## Source hierarchy

The hierarchy is contextual, not mechanically numerical. A lower-tier source on point can outweigh a higher-tier source off point, and a later-in-time rule can displace an earlier one. Use the default order below unless authority, date, or scope dictates otherwise.

### Tier 1 — Primary legal authority

Prefer:
- legislation.gov.uk — enacted and revised UK legislation, statutory instruments, schedules, commencement provisions, and territorial-extent annotations.
- commencement provisions and commencement orders — enactment is not commencement; Royal Assent or making does not prove a provision is in force.
- official explanatory notes — explanatory material only, not law. Never cite explanatory notes as the legal rule itself.
- binding court and tribunal judgments — UK Supreme Court; relevant appellate authority; High Court / Court of Appeal / Court of Session / Sheriff Appeal Court as applicable; UK tribunals of competent jurisdiction.
- official statutory codes of practice.
- binding regulator rules where the regulator has rule-making authority (record the rule-making power).

Record the exact provision, section, regulation, regulation number, paragraph, schedule, or article. Record territorial extent per provision where relevant.

### Tier 2 — Authoritative regulator material

Depending on subject matter, examples:
- Information Commissioner's Office (ICO) — data protection and privacy.
- Competition and Markets Authority (CMA) — consumer protection and competition.
- Financial Conduct Authority (FCA) — financial services and payments.
- Office of Rail and Road (ORR) — rail and road.
- Department for Transport (DfT) — transport policy and guidance.
- Equality and Human Rights Commission (EHRC) — equality and discrimination.
- Civil Aviation Authority (CAA) — aviation.
- Advertising Standards Authority (ASA) — advertising within its remit.
- Ofcom — communications.
- HM Revenue and Customs (HMRC) — tax.
- National Cyber Security Centre (NCSC) — cyber security guidance.
- Companies House — company information and filing.
- Other competent UK regulators or public bodies.

Do not assume a regulator applies merely because it discusses the topic. Prove the regulator's remit and the organisation/activity's applicability before using its material as authority.

### Tier 3 — Official government guidance

Use GOV.UK departmental guidance when relevant. Classify it as guidance unless it has a stronger legal status. Do not convert plain-language GOV.UK guidance into statutory text. Where GOV.UK summarises a rule, trace the rule back to legislation or regulator authority when the exact legal requirement matters.

### Tier 4 — Official standards and authoritative technical guidance

Examples:
- W3C and WCAG — web accessibility.
- British (BSI) or international (ISO) standards where applicable.
- NCSC — technical security guidance.
- OWASP — security controls.

Distinguish:
- legally incorporated standard (the standard is given legal force by reference);
- regulator-expected standard (the regulator expects it but it is not itself law);
- recognised good practice;
- voluntary technical guidance.

A technical standard does not establish a legal obligation unless law or a binding regulator rule incorporates it.

### Tier 5 — Official implementation documentation

Use official vendor, framework, browser, API, or provider documentation only for implementation semantics. It cannot establish legal obligations.

### Tier 6 — Secondary material

Secondary commentary (textbooks, practitioner works, law firm public guidance, reputable journalism) may help locate or interpret an issue, but must not be the sole authority for a material legal conclusion. Random blogs, marketing pages, AI-generated articles, forums, and social posts must never establish legal requirements.

## Mandatory official research sources

Use and record the following where relevant:

- legislation.gov.uk — for enacted and revised legislation, SIs, commencement, amendments, territorial extent, superseded versions, and explanatory notes.
- GOV.UK — for departmental guidance, consultations, and policy papers.
- Relevant regulator websites — for regulator rules, codes, decisions, enforcement notices, and guidance.
- Find Case Law from The National Archives — for court and tribunal judgments.
- UK Supreme Court judgments — for Supreme Court authority.
- Official tribunal or regulator decision databases — for enforcement and tribunal decisions.
- Official statutory-code repositories — for statutory codes of practice.
- Official consultation and policy-paper collections — for consultations and draft proposals (label as draft/consultation, not current law).
- Official archived material — where current pages refer to superseded guidance, use official archives, record that the material is archived, and verify whether it was superseded.

## Authority classification

Every external source must be classified as exactly one of:
- primary legislation;
- secondary legislation or statutory instrument;
- retained, assimilated, or otherwise continuing EU-derived law where relevant;
- binding court or tribunal decision;
- statutory code of practice;
- regulator rule;
- regulator decision or enforcement notice;
- regulator guidance;
- official government guidance;
- official consultation or draft proposal;
- official standard;
- industry code;
- vendor documentation;
- secondary commentary;
- community material;
- unknown authority.

Do not collapse these categories into "official source". The classification changes the weight, the wording permitted, and whether the proposition is a duty, an expectation, or mere advice.

## Legislation research

For each legislative proposition:

1. Locate the instrument on legislation.gov.uk. Record the exact title, year, and reference.
2. Identify whether it is primary legislation, secondary legislation/SI, or retained/assimilated EU-derived law.
3. Identify the exact section, regulation, paragraph, schedule, or article.
4. Check territorial extent per provision (UK-wide, GB, England and Wales, Scotland, Northern Ireland, overseas territories/Crown dependencies if actually relevant). Do not assume one extent applies to all sections.
5. Check commencement: Royal Assent/making date vs commencement date vs commencement order(s); staged commencement; territorial commencement.
6. Check amendments, repeals, prospective amendments, and outstanding changes — revised legislation is not complete without checking outstanding changes.
7. Check transitional, savings, and sunset provisions and temporary measures.
8. Record the version applicable to the repo document's date, the current version, and the version applicable to the organisation's intended launch/operation date.
9. Use explanatory notes only as explanatory material, never as the legal rule.
10. Do not reconstruct likely statutory wording from memory. If the text cannot be located and verified, record `unverified`.

## Regulator research

For each regulator proposition:

1. Identify the regulator and confirm its remit covers the organisation, activity, and affected group.
2. Confirm the organisation's legal role and applicability (see `jurisdiction_and_temporal_pack.md`).
3. Classify the material as: regulator rule (binding), statutory code, regulator decision/enforcement notice, regulator guidance, or official consultation/draft.
4. Describe accurately whether the material: interprets law; sets regulator expectations; is a statutory code; is formally binding; is evidential; or is advisory.
5. Check effective/revision/withdrawal dates and superseded versions.
6. Record publication date, effective date, and access date.

## Government-guidance research

For each GOV.UK proposition:

1. Classify as guidance unless it has a stronger legal status (e.g. it republishes a statutory instrument).
2. Do not convert plain-language guidance into statutory text.
3. Where guidance summarises a rule and the exact legal requirement matters, trace the rule back to legislation or regulator authority.
4. Record the department and publication date.

## Case-law research

Use case-law research when statutory meaning, legal interpretation, precedent, enforcement history, or disputed applicability depends on it. Do not make case-law research mandatory for every routine requirement.

Record for each case:
- court;
- jurisdiction;
- neutral citation;
- judgment date;
- precedential relevance (binding, persuasive, distinguishable, overturned, appealed, or otherwise uncertain where verifiable);
- appeal or overruling status where verified (whether the decision was affirmed, reversed, overruled, or is under appeal);
- relevance to the exact legal question (not merely topical relevance);
- factual distinctions (how the case's facts differ from the audited facts, where material);
- database coverage limitations;
- whether qualified legal research is needed.

Use Find Case Law from The National Archives, UK Supreme Court judgments, and official tribunal/regulator decision databases. Record which database was searched.

Limitation: The absence of a judgment from one database does not prove no relevant case exists. "No result found" is not "no case law exists." Record database and search limitations and, where the stakes are material, recommend qualified legal research. A case found but factually distinguishable is weaker authority for the exact question than its bare precedential label suggests — record the distinction.

Statutory meaning is ultimately a matter of law for the courts; regulator and government interpretations are persuasive indicators, not binding determinations of statutory meaning (unless a tribunal has so held).

## Statutory-code research

Locate official statutory codes of practice in the relevant regulator's official repository. Distinguish a statutory code (given legal force by statute) from informal regulator guidance. Record the enabling provision, effective date, and whether breach gives rise to a right of action or only evidential weight.

## Citation discipline

Keep quotations short and exact. Do not fabricate quotation marks around paraphrases. For each citation record:
- Source ID (stable, matching the source register).
- Title.
- Publisher/body.
- Source type (from the authority classification list).
- Authority tier.
- URL.
- Jurisdiction.
- Citation or reference (e.g. section, regulation, paragraph).
- Publication date; effective date; access date.
- Current/superseded/draft/archived status.
- Quoted or closely paraphrased proposition (exact words verified: yes/no).
- Applicability conditions.
- Known amendments or outstanding changes.
- Conflicting authority.
- Research limitations.

Use `source_record_template.md` for the full per-source record.

## Quotation and paraphrase taxonomy

Every proposition record must declare one of three labels. Never put quotation marks around a paraphrase; never quote more than necessary; always record the section, regulation, paragraph, schedule, or page heading where available.

- **Exact verified quotation** — verbatim words from the located source, in quotation marks, with the exact location recorded. Mark `Exact words verified: yes`. Re-verify by re-reading; do not rely on memory.
- **Close paraphrase** — a paraphrase of the located source's proposition, marked as a paraphrase, with the exact location recorded so it can be checked. Mark `Exact words verified: no`. Do not use quotation marks. A close paraphrase is weaker than an exact quotation and must not be presented as the source's words.
- **Auditor interpretation** — a conclusion drawn by the auditor from one or more sources, marked explicitly as interpretation, with the sources it relies on recorded. Mark `Exact words verified: no` and label as interpretation. An auditor interpretation is the weakest form and must not be cited as the source's own wording. Where an interpretation bears on a material legal question, flag it for qualified legal review.

A proposition presented without a label defaults to `Auditor interpretation` and is treated as the weakest form until re-labelled with verification.

## Source-conflict handling

When GOV.UK guidance, regulator guidance, legislation, and case law appear inconsistent:
- do not average them;
- rank by authority (use the default tier order and check for higher or later authority);
- check dates (which source is the most recent);
- check scope (which source governs this exact issue and jurisdiction);
- check whether one source summarises another (a guidance summary does not override the legislation it summarises);
- record the conflict in the audit artifact's conflict register;
- escalate unresolved legal interpretation (status: `Legal interpretation unresolved` or `Qualified legal review required` as applicable).

## Research question and result format

Stage 4 produces a legal question per material claim. Stage 5 answers that specific question — do not conduct unlimited legal browsing. For each:

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

The research result references the source register entries that answer the question. If no source could be located and verified, record `unverified` and do not assert the proposition. A `no source found` result is recorded with its limitations and is never treated as proof of the negative.

## Research freshness and re-check policy

Every material source must record: access date; publication/revision date; effective date; current/superseded/draft/archived status; and review-by date where appropriate. Authority can change; a conclusion is only as current as its access date.

Different legal domains drift at different rates. Do not invent a universal fixed expiry where different domains require different review frequency. Use the per-domain re-check cadence in `compliance_drift.md` as the default, and record a per-source override where domain-specific authority dictates a different cadence. A material event (commencement, withdrawal, enforcement notice, provider notice, reform announcement) triggers an immediate re-check regardless of cadence.

For volatile regulator guidance (e.g. ICO, FCA, CMA) and GOV.UK pages, prefer a shorter re-check cadence (3–6 months) and re-check the publication/revision date on each access. For in-force legislation, re-check on known legislative events and at least every 6 months. For official standards with discrete version releases (WCAG, ISO, BSI, NCSC), re-check on known release. For case-law authority, precedential status changes are event-driven; re-check when a material new judgment appears or the specific question's interpretation is disputed.

Record `review-by date` per source in the source register. A source past its review-by date without re-check is itself a freshness signal; record `stale: re-check needed` rather than relying on it as current authority. Absence of visible change is not proof no drift occurred (see `compliance_drift.md`).