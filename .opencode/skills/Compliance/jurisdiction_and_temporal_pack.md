# Jurisdiction and Temporal Pack

Read this file during Stage 4 (legal-question formulation), Stage 6 (requirement normalisation), and the applicability and temporal analysis sections of the audit. The UK is not one uniform legal jurisdiction, and a rule in force on one date may not be in force on another. This pack controls both dimensions.

## UK jurisdiction distinctions

Never assume "UK law" is one uniform set of rules. Determine, where relevant:

- United Kingdom-wide applicability.
- England and Wales.
- Scotland.
- Northern Ireland.
- Great Britain (England, Wales, Scotland; excludes Northern Ireland).
- Overseas territories or Crown dependencies (only if actually relevant — never assumed).

Primary legislation often extends to only part of the UK. Secondary legislation and commencement orders can have territorial scope narrower than the parent Act. Check the territorial-extent annotation on legislation.gov.uk per provision, not per Act.

## Devolved and reserved subject matter

Determine whether a subject is reserved to the UK Parliament or devolved to the Scottish Parliament, Senedd Cymru, or Northern Ireland Assembly. Do not silently apply England-and-Wales guidance to Scotland or Northern Ireland. Where devolved competence differs, record both positions and check which applies to the organisation's place of establishment and place of supply.

## Legal-role analysis

Determine the organisation's legal role for each requirement:

- controller, processor, joint controller;
- employer;
- trader;
- platform, intermediary, operator;
- provider of services;
- public-sector body vs private-sector body;
- other relevant role.

The role determines which duties apply. Do not assume a role; record the evidence for it (registered office, place of central administration, contractual position, nature of the activity).

## Affected persons

Identify the affected group for each requirement:

- employee, worker, contractor, applicant;
- customer, consumer, passenger;
- child, vulnerable person;
- data subject;
- other affected group.

A rule protecting consumers may not apply in a B2B context; a rule protecting children may trigger additional duties. Record B2B vs B2C context explicitly.

## Applicability ladder

For each requirement, record an `Applicability status` with the evidence supporting it:

- `applies` — evidence shows the rule governs this organisation, activity, jurisdiction, and affected group for the relevant period.
- `likely applies` — strong evidence but one fact remains to be confirmed.
- `may apply` — material facts are unresolved; do not conclude as though it applies.
- `does not appear to apply` — evidence suggests non-applicability; record why and the risk if wrong.
- `unresolved` — applicability cannot be determined from available evidence; do not continue as though the rule applies; escalate as needed.

If applicability is unresolved, record the missing facts needed to resolve it. Do not treat an unresolved rule as either applying or not applying.

## Thresholds and exemptions

Check whether a duty is triggered by a threshold (turnover, staff count, number of data subjects, volume of processing, number of passengers, amount of a fee) or excluded by an exemption. Record the threshold value, the source, and the organisation's measured value if available. If the organisation's value is not available from repo evidence, mark applicability `unresolved` or `deployment dependent` as appropriate.

## Effective dates

Every legal or regulatory conclusion must be date-aware. Check, where relevant:

- date made or enacted;
- Royal Assent where relevant;
- commencement date;
- commencement orders;
- staged commencement;
- territorial commencement;
- amendments;
- repeals;
- prospective amendments;
- outstanding changes;
- transitional provisions;
- savings provisions;
- sunset provisions;
- temporary measures;
- effective date of regulator guidance;
- publication date;
- revision date;
- withdrawal date;
- superseded versions;
- consultation status;
- draft versus final status;
- enforcement grace periods.

## Commencement checks

Enactment, Royal Assent, or making of an instrument does not automatically prove that every provision is in force. Require a commencement check:

- Find the commencement provision or commencement order on legislation.gov.uk.
- Identify whether commencement is automatic on Royal Assent, on a fixed date, by subsequent order, or staged.
- Identify any provisions not yet commenced.
- Record the date each relevant provision came/will come into force.
- For staged commencement, record the stage applicable to the relevant date.

If commencement cannot be verified, mark the requirement's effective date `unverified` and do not assert it is in force.

## Amendments and superseded material

Check the legislation's amendment history and outstanding changes. Revised legislation on legislation.gov.uk may not show prospective amendments not yet in force. Record:

- the version applicable to the repo document's issue date;
- the current version;
- the version applicable to the organisation's intended launch or operation date.

Where regulator or government guidance has been superseded, locate the current version. Where a current page refers to superseded guidance, use official archives, record that the material is archived, and verify whether it was superseded.

## Transitional, savings, and sunset provisions

A repeal or amendment may not extinguish existing rights or obligations if transitional or savings provisions apply. A temporary or sunset measure may lapse on a fixed date. Record these and check the relevant date against them.

## Historical versus current-law comparison

Compare:

- the law at the repo document's issue date;
- the current law;
- the law applicable to the organisation's intended launch or operation date.

Do not retroactively label a historically accurate document wrong without context. A document accurate at its issue date may be outdated now without having been wrong when published. Record both.

## Draft legislation and consultations

Label clearly:

- `draft` — a bill or draft instrument not yet enacted.
- `consultation` — a consultation inviting responses.
- `proposed code` — a draft code not yet in force.
- `pending approval` — awaiting a Parliamentary or regulatory approval step.
- `not yet in force` — enacted but uncommenced, or made but not yet effective.

Do not convert future proposals into current duties. A consultation document cannot be cited as the current law. A bill cannot be cited as law until enacted (and then only when commenced).

## Future or draft law handling

Where the repo document anticipates a future legal change, record the change as `pending` and the current rule as the governing rule for today. Do not assert the future rule as a current duty. Where a future rule affects the organisation's intended launch date, record the future effective date and flag that the requirement's applicability is date-dependent.

## Temporal record fields

Every source record (see `source_record_template.md`) must include:

```text
Source date:
Effective date:
Research/access date:
Version/status:
Temporal applicability:
Outstanding-change check:
Superseded-material check:
```