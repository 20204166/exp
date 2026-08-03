---
pack: accessibility.wcag-22
version: 2026-07
authorities:
  - W3C WCAG 2.2
  - W3C Understanding WCAG 2.2
load_when:
  - any accessibility audit
  - form, modal, dialog, menu, table, dropdown
  - public-facing surface
rules:
  - Perceivable: text alternatives, captions, contrast, resize/reflow at 320px CSS px, non-text contrast >= 3:1
  - Operable: keyboard reachable, no keyboard trap, focus visible (2.4.7), focus order (2.4.3), target size >= 24x24 CSS px (2.5.8), bypass blocks
  - Understandable: error identification (3.3.1), labels (3.3.2), status messages (4.1.3)
  - Robust: name/role/value (4.1.2), status messages programmatically determined
  -Reduced motion: respect prefers-reduced-motion (2.3.3 Animation from Interactions)
validation_checks:
  - axe-core run per viewport x state
  - keyboard-only walkthrough of touched controls
  - contrast check (text + non-text)
  - resize to 320px width, no horizontal scroll, no clipped content
  - zoom to 200%, content still usable
false_positives:
  - "needs review: heading skipped" when visually hidden heading exists for assistive tech
  - "color-contrast: insufficient" on decorative non-text elements
framework_notes:
  - WCAG 2.2 minimum target; if repo targets 2.1 AA, do not relax 2.2-added criteria silently
report_snippets:
  - "Contrast: text 4.5:1, non-text 3:1, focus indicator 3:1 against adjacent colours"
  - "Target size: 24x24 CSS px minimum on touched controls"
anti-patterns:
  - removing visible focus styling
  - relying on hover-only affordances for touch
  - using aria-label that differs materially from visible label
---

# Pack: WCAG 2.2 accessibility

Authoritative source: W3C WCAG 2.2. Treat automated axe scans as partial coverage; manual keyboard walkthrough is required for touched interactive controls.

Key criteria this pack applies by default:

- 1.4.3 Contrast (Minimum) — text 4.5:1, large text 3:1
- 1.4.11 Non-text Contrast — 3:1
- 1.4.10 Reflow — 320 CSS px wide, no 2D scroll
- 2.1.1 Keyboard
- 2.4.3 Focus Order
- 2.4.7 Focus Visible
- 2.4.11 Focus Not Obscured (Minimum) — 2.2
- 2.5.8 Target Size (Minimum) — 24x24 CSS px (2.2)
- 3.3.1 Error Identification
- 3.3.2 Labels or Instructions
- 4.1.2 Name, Role, Value
- 4.1.3 Status Messages
- 2.3.3 Animation from Interactions — honour prefers-reduced-motion

If a higher conformance level is required (AA vs A), set it in the change plan before validation; do not silently upgrade or relax.