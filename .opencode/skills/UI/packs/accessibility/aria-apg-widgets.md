---
pack: accessibility.aria-apg-widgets
version: 2026-07
authorities:
  - W3C WAI-ARIA Authoring Practices Guide (APG)
  - W3C ARIA 1.2
load_when:
  - custom dropdown
  - modal / dialog
  - combobox / listbox
  - tabs
  - accordion
  - menu / menubar
  - tree
  - breadcrumb
rules:
  - Prefer native HTML controls wherever they meet the requirement
  - When native is insufficient, follow the APG keyboard interaction model exactly
  - Focus must be visible and programmatically managed (roving tabindex / aria-activedescendant per APG)
  - Roles: only add ARIA roles when semantics not expressible in HTML
  - aria-label may be valid when a visible label is absent but text label is awkward; prefer visible label
  - Do not duplicate role semantics (e.g. role="button" on <button>)
validation_checks:
  - keyboard model matches APG for the widget type (arrows / home / end / type-ahead where specified)
  - focus moves predictably on open/close
  - escape closes menu/popover
  - focus returns to trigger on close
  - clicking outside closes popover and restores focus
  - screen-reader announces open/closed state when applicable
false_positives:
  - "role redundant" warnings on elements that need predictable cross-browser semantics — review case by case
  - "aria-label on button without text" — valid only when text label is genuinely not shown
anti-patterns:
  - inventing keyboard models that differ from APG
  - using aria-hidden on focusable elements
  - using div+role=button without disabled/tabindex handling
report_snippets:
  - "Combobox keyboard model: APG combobox; arrow up/down to traverse, Home/End, type-ahead"
  - "Dialog: focus trap, escape closes, focus returns to trigger"
framework_notes:
  - APG patterns are a starting point, not law; some patterns need design-language adjustment. Document deviation explicitly.
---

# Pack: ARIA / APG widgets

Custom widgets require a keyboard interaction model and managed focus. The APG is the default reference. A widget may deviate from APG only with explicit justification recorded in the change plan.

Native HTML is preferred. `<select>`, `<details>`, `<dialog>`, native `<button>`, `<input>` supply role/value/keyboard for free. Custom widgets exist when styling or composition constraints make native impossible; the cost of that choice is the keyboard model.

Use APG references for: combobox, listbox, menu, menubar, menu-button, tabs, tablist, accordion, tree, treegrid, dialog, alertdialog, breadcrumb, disclosure, link button patterns.

Reduced-motion: a custom widget that animates open/close must respect `prefers-reduced-motion` — collapse to instant transitions.