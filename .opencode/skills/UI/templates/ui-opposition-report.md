# UI Opposition Report — {surface}

Authoritative artifact for Stage 9. Each critic writes its own section directly into this file. The orchestrator must not backfill, summarise, or simulate critic sections. If a critic cannot write its section, mark `status: incomplete` and report an orchestration gap.

Conforms to `schemas/opposition.schema.json` (machine-readable companion: `ui-opposition.json`).

---

## Header (orchestrator-owned)

- Surface slug: {slug}
- Mode: {mode}
- Risk: {low | medium | high | design-system-altering}
- Critic set used: {escalation chosen at Stage 0}
  - {opposition-critic}
  - {visual consistency | accessibility | css architecture | responsive | scope | smaller-fix — only if escalated}
- Status: {complete | incomplete}
- Incomplete reason: {if applicable}

Inputs read by opposition:
- `.ui/{slug}/surface-map.json`
- `.ui/{slug}/design-language.md`
- `.ui/{slug}/reports/ui-audit.json`
- `.ui/{slug}/reports/ui-change-plan.md`
- `.ui/{slug}/evidence/`

## Findings index

| Finding | Change | Surface | Decision |
|---|---|---|---|
| OPP-001 | ... | visual consistency | ACCEPT / ... |
| OPP-002 | ... | accessibility | ACCEPT WITH MODIFICATION |
| ... | | | |

## Per-critic sections

Each critic writes its section below using the finding template. The orchestrator fills nothing here.

### Opposition critic

(OPPOSITION-CRITIC writes here.)

### Visual consistency critic

(Only if escalated. CRITIC writes here.)

### Accessibility critic

(Only if escalated. CRITIC writes here.)

### CSS architecture critic

(Only if escalated. CRITIC writes here.)

### Responsive critic

(Only if escalated. CRITIC writes here.)

### Scope / regression critic

(Only if escalated. CRITIC writes here.)

### Smaller-fix critic

(Only if escalated. CRITIC writes here.)

## Finding template (used by every critic)

```text
Finding OPP-NNN
Proposed change: <summary>
Challenge surface: <visual consistency | accessibility | css architecture | responsive | scope | smaller-fix>
Decision: ACCEPT | ACCEPT WITH MODIFICATION | BLOCK | DEFER | NEEDS EVIDENCE | HAND OFF TO BUGGUARD
Reason: <one or two sentences citing surface-map / design-language / evidence>
Safer alternative: <required when decision is not ACCEPT>
Evidence cited: <paths to evidence bundle rows>
```

## Worked example (for reference; remove before publishing)

```text
Finding OPP-003
Proposed change: Increase all card padding from 16px to 28px.
Challenge surface: visual consistency
Decision: BLOCK
Reason: The product uses compact admin density. 28px appears only on marketing sections. This reduces table scanability and creates inconsistent density.
Safer alternative: Use existing --space-5 only on the empty-state card, not all cards.
Evidence cited: design-language.md (density: compact), evidence/screenshots/before/dashboard-default-1280.png
```

## Synthesis handoff

The orchestrator's Stage 10 synthesis reads this file and produces `ui-change-plan.md`. Synthesis may begin only after every required critic section exists and is written by the assigned critic. A missing section blocks synthesis — do not paper over with summaries.