# Core — Audit Taxonomy

Stage 6. Typed audit modes, the issue schema, severity, confidence, and the visual-debt taxonomy.

## Typed audit modes

A single universal audit becomes generic and noisy. Use the mode chosen at Stage 0 and focus checks accordingly.

| Mode | Primary checks |
|---|---|
| visual polish | spacing rhythm, alignment, hierarchy, contrast, decoration coherence |
| css architecture | cascade, specificity, layers, tokens, leakage, dead CSS, override hacks |
| design-system cleanup | duplicate tokens, duplicate spacing, duplicate colours, inconsistent variants |
| accessibility | semantics, landmarks, headings, labels, name/role/value, keyboard, contrast, reduced motion |
| responsive | viewport/container behaviour, overflow, horizontal scroll, breakpoint correctness, container queries |
| interaction | state coverage (hover/focus/active/disabled/loading/error/success), feedback pairs, microinteraction triggers |
| component state | state matrix coverage, default/hover/focus-visible/active/disabled/loading/empty/error/success/selected/expanded/long/short/permission-denied/network-error |
| visual regression | before/after diffs, viewport diffs, state diffs |
| implementation | result against accepted change plan |

A `full surface refinement` runs multiple modes — sample the modes per surface (see `surface-discovery.md`).

## Issue schema

Every issue must conform to `schemas/ui-audit.schema.json`. Machine-readable view is `.ui/<surface-slug>/reports/ui-audit.json`; human-readable summary lives in `ui-audit.md`.

```json
{
  "id": "UI-014",
  "surface": "claims/new",
  "mode": "visual polish",
  "category": "spacing",
  "severity": "medium",
  "confidence": "high",
  "evidence": [
    "screenshot: mobile-375/default",
    "css: static/css/forms.css:122",
    "dom: form field group"
  ],
  "design_language_fit": "violates existing 8px spacing rhythm",
  "user_impact": "form feels cramped and scanability is reduced",
  "recommended_fix": "use existing --space-4 token between field groups",
  "regression_risk": "low",
  "validation": ["mobile screenshot diff", "desktop screenshot diff"]
}
```

Required fields all populated. Evidence arrays are real citations; do not invent paths or selectors.

## Categories (visual-debt taxonomy)

Issues are tagged with one or more visual-debt categories:

- **layout debt** — broken grid, overlap, alignment drift
- **spacing debt** — inconsistent rhythm, missing scale usage
- **typography debt** — scale drift, missing weights, wrong line-height
- **colour debt** — hardcoded colours, contrast failures, missing semantic mapping
- **component drift** — same control rendered differently across surfaces
- **state debt** — missing hover/focus/active/disabled/loading/empty/error
- **responsive debt** — overflow, horizontal scroll, breakpoint regressions
- **accessibility debt** — semantics, focus, contrast, keyboard, reduced motion
- **css architecture debt** — specificity escalation, leakage, duplicate rules, override hacks
- **interaction feedback debt** — missing trigger/feedback pairing, dead microinteractions

## Severity

| Severity | Meaning |
|---|---|
| Critical | inaccessible / unusable / broken layout |
| High | major visual or interaction quality problem |
| Medium | inconsistency or polish issue users notice |
| Low | minor refinement |
| Deferred | valid but outside current scope |
| Blocked | unsafe or inconsistent with design language |

Do not inflate. Do not downgrade accessibility/layout impact because the fix is easy.

## Confidence per issue

Each issue carries a confidence tier from `evidence-model.md`. Issue-level confidence is the minimum evidence tier across all cited evidence. An issue whose only evidence is "screenshot looks cramped" without the underlying CSS row is Tier 2 Medium at most.

Issues that cannot reach the required confidence for their severity (High needs Tier 4; Critical needs Tier 4 unless evidence_availability is `code only` — then Critical is not claimable) are marked `needs evidence`, not validated.

## Triage (Stage 7)

Prioritise issues by:

1. user-visible impact
2. accessibility risk
3. layout breakage
4. design-system inconsistency
5. surface importance
6. implementation safety
7. scope

Output feeds Stage 8 change-plan generation.

## Escalation to opposition

Escalate an issue to full opposition (Stage 9) when any of:

- severity High or Critical
- confidence Medium or below for a Medium+ severity issue
- design_language_fit is `violates` and the fix changes more than one component
- regression_risk is `medium` or `high`
- the change touches a BugGuard-owned boundary (route to BugGuard instead)

Otherwise the single Opposition Critic suffices. Full opposition is escalated, not default.

## What audit must not do

- Do not file issues for "ugly" without naming the violated design-language contract.
- Do not file issues that require changes outside UI's ownership (route to BugGuard).
- Do not file issues from Tier 0 evidence.
- Do not combine unrelated dimensions into a single issue (one category per issue; related issues link by id).