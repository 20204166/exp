---
pack: validation.keyboard-testing
version: 2026-07
authorities:
  - W3C APG keyboard interaction
  - W3C WCAG 2.1.1 / 2.4.3 / 2.4.7
load_when:
  - accessibility fix
  - custom widget
  - any flow involving forms / modals / menus / tabs / comboboxes
rules:
  - Manual keyboard walkthrough is required for touched interactive controls; automated scan is partial coverage only
  - Focus order follows reading order; do not manipulate tab order via tabindex without reason
  - Focus must be visible (2.4.7) and not entirely obscured (2.4.11)
  - Modal: focus trap + escape closes + focus returns to trigger
  - Menu / combobox: APG keyboard model
validation_checks:
  - tab traversal covers the touched controls in expected order
  - shift+tab reverses
  - enter/space activates
  - escape closes overlays
  - focus visible at every touched state
false_positives:
  - "tab order skipped element" where element is intentionally tabindex=-1 (e.g. managed focus via JS)
---

# Pack: Keyboard testing

Automated a11y scanners (axe) flag keyboard issues but cannot prove keyboard usability. A manual keyboard walkthrough is required for any accessibility fix or custom widget:

1. Identify touched interactive controls from the surface map.
2. Tab through them in expected reading order.
3. Verify Enter/Space activates, Escape closes overlays, focus returns to triggers.
4. Verify focus-visible contrast at every state.
5. For custom widgets, walk the APG keyboard model (arrows/Home/End/type-ahead per widget type).

Record the walkthrough in `evidence/accessibility/keyboard-trace.md`. A keyboard trace is required evidence for accessibility-fix mode and for any change touching a custom widget.