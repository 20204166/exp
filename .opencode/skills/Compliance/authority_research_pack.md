# Authority Research Pack

Primary reviewer: Reviewer 1 — Authority & Currency Reviewer.

Use this pack to prove the cited legal or regulatory authority is real, current, correctly weighted, and usable for the audited proposition. Do not use it to decide whether the organisation complies.

## Owned question

```text
Is the authority itself correct, current, commenced, and weighted properly for the proposition asserted?
```

## Hard boundary

Reviewer 1 must never analyse repository implementation, deployment configuration, operational practice, consumer harm, commercial impact, or whether the organisation's facts satisfy the law beyond recording applicability conditions stated in the source.

## Source hierarchy

Rank sources contextually, not mechanically:

- Tier 1: primary legislation, secondary legislation/statutory instruments, commencement orders, binding court/tribunal decisions, statutory codes, binding regulator rules.
- Tier 2: competent regulator material, including enforcement decisions, statutory guidance, non-binding guidance, and official regulator codes.
- Tier 3: GOV.UK departmental guidance.
- Tier 4: official standards and technical guidance where legally incorporated, regulator-expected, recognised good practice, or voluntary.
- Tier 5: official vendor/provider/framework documentation for implementation semantics only.
- Tier 6: secondary commentary, used only to locate or contextualise authority.

Do not average conflicting sources. Prefer higher, later, more specific authority on the exact issue and jurisdiction. Record unresolved conflict as `Authority conflict` or `Legal interpretation required`.

## Mandatory official-source path

Use and record relevant searches/accesses from:

- legislation.gov.uk for enacted/revised legislation, statutory instruments, schedules, commencement, extent, amendments, repeals, and outstanding changes.
- GOV.UK for departmental guidance, consultations, policy papers, and official archived material.
- Relevant regulator websites for rules, codes, guidance, decisions, enforcement notices, and consultations.
- Find Case Law from The National Archives and UK Supreme Court judgments where precedent, statutory interpretation, enforcement history, or disputed applicability depends on case law.
- Official tribunal/regulator decision databases where the regulator or tribunal has issued relevant decisions.
- Official archives where a current page refers to superseded, withdrawn, or historic guidance.

Never cite a search-result snippet, AI summary, memory, or secondary article as authority for a material legal proposition.

## Legislation.gov.uk checks

For each legislative source:

1. Locate the exact instrument and record title, year, chapter/SI number, and URL.
2. Classify the source: primary legislation, secondary legislation/SI, retained/assimilated EU-derived law, or other.
3. Record the exact section, regulation, article, paragraph, or schedule.
4. Check territorial extent per provision, not merely per Act.
5. Check commencement. Royal Assent, enactment, making, or publication is not enough.
6. Check commencement orders, staged commencement, territorial commencement, transitional provisions, savings provisions, sunsets, and temporary measures.
7. Check amendments, repeals, prospective amendments, and outstanding changes.
8. Compare the version at document issue date, current date, and planned operational date.
9. Record whether the revised text is up to date and whether outstanding effects exist.
10. Use explanatory notes only as explanation, never as the legal rule.

If text cannot be located or commencement cannot be verified, record `unverified` and do not assert that the provision is in force.

## Guidance and regulator checks

For each regulator or GOV.UK source:

1. Confirm the publisher/body and whether it is competent for the issue.
2. Classify the source as regulator rule, statutory code, regulator decision/enforcement notice, regulator guidance, official government guidance, official consultation/draft, or other.
3. Record whether it is binding, evidential, interpretive, expected practice, advisory, or draft.
4. Check publication date, revision date, effective date, withdrawal date, and supersession.
5. Locate current version where a source is archived, withdrawn, or superseded.
6. Do not convert plain-language guidance into statutory text.
7. Where guidance summarises a rule and exact legal duty matters, trace the duty back to legislation, statutory code, regulator rule, or case law.

## Case-law checks

Use case-law research only when statutory meaning, interpretation, precedent, enforcement history, or disputed applicability depends on it. It is not mandatory for every routine requirement.

Record:

```text
Court:
Jurisdiction:
Neutral citation:
Judgment date:
Database searched:
Precedential relevance:
Appeal/overruling status where verified:
Relevance to exact legal question:
Factual distinctions:
Coverage limitations:
Qualified legal research needed:
```

Absence from one database is not proof no case exists. A distinguishable case is weaker authority for the exact question than its citation alone suggests.

## Source record discipline

Use `source_record_template.md` for every external source. Each material proposition must state whether it is:

- exact verified quotation;
- close paraphrase;
- auditor interpretation.

Never place quotation marks around a paraphrase. Keep quotations short and exact.

## Reviewer 1 output

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
