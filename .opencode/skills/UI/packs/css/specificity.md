---
pack: css.specificity
version: 2026-07
authorities:
  - MDN Specificity
  - W3C CSS selectors
load_when:
  - css architecture audit
  - override attempts
  - introducing a new selector
rules:
  - Specificity is computed: inline > ID > class/attribute/pseudo-class > type/pseudo-element
  - Highest-touch selectors should have the lowest specificity (base, utilities)
  - Component scopes use medium specificity (class + optional state)
  - !important wins vs the cascade but loses to specificity-improving refactors; avoid for new code
  - Specificity escalation across files is a maintainability bug
validation_checks:
  - compute before/after highest selector specificity on touched files
  - net !important count must not increase without explicit justification
  - no new selector matches outside the component scope unless global style intended
false_positives:
  - "high specificity" on a single utility class selector that legitimately overrides per-use (review)
anti-patterns:
  - piling descendant selectors (.parent .child .grandchild .button) to win overrides
  - ID selectors for components (use class)
  - !important for "just in case"
  - "!important war" where competing rules both escalate
report_snippets:
  - "Highest specificity touched: (0,2,1) -> (0,2,0) — no escalation"
framework_notes:
  - Scoped CSS (Vue scoped, CSS Modules) attaches a data attribute; specificity effectively becomes (0,2,0) per selector
---

# Pack: CSS specificity

Specificity is the mechanism that decides which rule wins at the same source order. Escalating specificity to win overrides is the most common source of maintainability debt.

Prefer lower specificity by default. Component styles should be predictable: a class selector plus optionally a state class. Utility styles belong at the same specificity level as other utilities.

`!important` is a tool, not a fix. New `!important` must not increase without a written reason in the change plan and an accepted justification in opposition.