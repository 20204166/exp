# UI Change Plan — {surface}

Stage 8 proposed plan and Stage 10 synthesised plan. The orchestrator owns this file.

Two halves:

1. **Proposed plan** (Stage 8) — the auditor's proposed change set, written before opposition.
2. **Synthesised plan** (Stage 10) — the accepted/modified/rejected set, written after opposition.

Implementation (Stage 11) follows only the synthesised half.

---

## Proposed plan (Stage 8)

- Surface slug: {slug}
- Mode: {mode}
- Risk: {low | medium | high | design-system-altering}
- Plan date: {date}

### Triage bands

| Band | Issue ids | Rationale |
|---|---|---|
| must fix | | user-visible impact / accessibility critical |
| should fix | | consistency / important debt |
| optional polish | | minor refinements |
| defer | | valid, outside scope |
| do not touch | | unsafe / BugGuard-owned / new visual language not requested |

### Proposed changes

For each proposed change:

```text
UI-NNN
proposed_change: <one sentence>
issue_supporting: <id>
proposed_files: <list>
token_or_variant_reused: <name or "none — proposed new, justification below">
justification_if_new: <required if no reuse>
estimated_regression_risk: low | medium | high
validation_required: <viewport x state, a11y, css-arch checks>
opposition_required: yes | no (escalation reason if yes)
```

### UI budget at proposal

```text
max new hardcoded colours: 0
max new arbitrary spacing values: 0
max new !important: 0
max specificity increase: none without reason
max new global selectors: 0
max new dependencies: 0 unless justified
min viewport coverage: 3 (smallest / mid / largest target)
min state coverage: default / error / loading / focus-visible
```

Any value exceeding the budget at proposal must be justified inline.

## Synthesised plan (Stage 10)

Filled in after `ui-opposition-report.md` is complete.

### Decisions summary

| Change | Decision | Critic | Modification |
|---|---|---|---|
| UI-NNN | accepted / modified / blocked / deferred / needs evidence / BugGuard handoff | {role} | {safer alternative if modified} |

### Accepted implementation order

1. {UI-NNN — files, order, validation}
2. ...

### Rollback notes (for medium+ regression risk)

- UI-NNN: files touched: <list>; prior values: <list>; rollback action: <replace / git revert path / token name restored>.

### BugGuard handoffs

| Issue | Reason | Evidence |
|---|---|---|
| UI-NNN | <one sentence naming the non-UI surface> | <paths> |

### Validation gates to be exercised (Stage 12-14)

- Static: <specificity delta check, hardcoded value check, etc.>
- Render: <viewport x state set>
- Accessibility: <axe + keyboard trace + reduced-motion>
- CSS architecture: <specificity / tokens / layers>

## Anti-generic-AI certification (one sentence)

> This plan reuses {tokens/variants}; introduces {N} new visual decisions, each justified and opposition-accepted; introduces {N} new dependencies (zero unless explicitly justified).