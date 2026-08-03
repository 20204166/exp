# Compliance Drift

Read this file when re-checking a prior audit (or prior compliance document set) against current law, guidance, implementation, and deployment. Compliance drift is a delta re-audit mode, not a fresh broad audit. It detects whether previously-verified conclusions remain valid and whether new changes require re-audit.

Drift review is a separate mode from the staged one-time audit in `compliance_document_audit.md`. Use it after a prior audit exists or after material change to law, guidance, the repo, or deployment.

## What drift detects

Check whether any of the following changed since the previous research date:

- legislation changed (amendment, repeal, prospective amendment became effective);
- commencement changed (an uncommenced provision commenced; a staged provision reached a new stage);
- outstanding amendments became effective;
- regulator guidance was revised or withdrawn;
- official URLs moved;
- policy citations became stale;
- a consultation became final guidance or law;
- a bill did not become law (expected commencement did not occur);
- internal documents passed their review-by date;
- implementation changed after the compliance review;
- deployment changed after the compliance review;
- provider terms or data-location information changed;
- organisation role or regulated activity changed.

Do not claim that absence of visible change proves no legal drift. A page that appears unchanged may have been superseded by a document not yet located; a URL that resolves may serve different content; a regulator that has not published may still have changed policy. Record what was checked and the limitations.

## Drift review record

For each prior audit, source, or document re-checked:

```text
Drift ID: DRFT-NNN
Previous research date:
Current research date:
Previous source/version:
Current source/version:
Change identified: none / amendment / repeal / commencement / revised guidance / withdrawn guidance / URL moved / citation stale / consultation became final / bill lapsed / review-by passed / implementation changed / deployment changed / provider terms changed / org role changed
Legal significance:
Repository documents affected:
Implementation surfaces affected:
Re-audit required: yes / no / partial
```

## Drift workflow

1. Identify the prior audit or prior document set and its research date(s).
2. For each material source in the prior source register, re-access it and compare current vs prior version/publication/effective/withdrawal status.
3. For each legislation source, re-check commencement, amendments, and outstanding changes against the current date.
4. For each guidance source, re-check whether it is still current, revised, or withdrawn; locate the current version if superseded.
5. For each internal compliance document, check its review-by date against today and whether implementation/deployment has changed since the prior audit.
6. For each provider-dependence finding, check whether provider terms, data-location, or subprocessor information changed. Provider change evidence may be unavailable from the repo — record `evidence unavailable from repository`.
7. Record a drift entry per item re-checked.
8. Where drift is identified, determine legal significance, affected repo documents/surfaces, and whether re-audit is required.
9. Where re-audit is required, scope a new `COMP-YYYYMMDD-NNN` audit referencing this drift review.

## Drift and per-domain re-check policy

Different legal domains drift at different rates. Do not apply a single universal expiry. Use the following default re-check policy unless domain-specific authority dictates otherwise; record a per-domain override where used:

| Domain class | Default re-check cadence | Reason |
|---|---|---|
| Primary/secondary legislation in force | 6 months or on known legislative event | legislation changes are discrete events but commencement orders and amendments can appear between revisions |
| Retained/assimilated EU-derived law | 6 months | sunset and reform programmes ongoing |
| Regulator guidance | 3–6 months; sooner for volatile regulators (ICO, FCA, CMA) | guidance is revised and withdrawn frequently |
| GOV.UK departmental guidance | 6 months or on known policy change | guidance pages are updated without version bumps |
| Case-law authority | not time-limited (status changes are event-driven); re-check on material question change | precedential status changes are discrete events |
| Official standards (WCAG/ISO/BSI/NCSC) | 12 months or on known version release | versions are discrete releases |
| Provider/vendor documentation | 3 months or on provider notice | provider terms and data-location change without repo visibility |

These are defaults, not absolute expiry dates. A material event (commencement, withdrawal, enforcement, provider notice) triggers an immediate re-check regardless of cadence. Record the actual re-check date per source.

## Drift limitations

- Absence of visible change is not proof no drift occurred.
- A page that appears unchanged may not be the current authoritative version.
- A regulator that has not published may still have changed policy or enforcement posture.
- Implementation and deployment drift may not be visible from repo evidence alone.
- Provider-terms drift is often invisible from the repo.
- A stale internal document past its review-by date is itself a drift signal regardless of external change.

Where drift cannot be ruled out, record `Drift cannot be excluded` and the reason rather than asserting stability.