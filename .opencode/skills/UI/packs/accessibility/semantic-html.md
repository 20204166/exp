---
pack: platform.html-semantics
version: 2026-07
authorities:
  - HTML Living Standard
  - MDN HTML element reference
load_when:
  - any UI change that adds or alters markup
rules:
  - Use the most specific native element (button, a, label, fieldset, legend, nav, main, header, footer, section, article, aside)
  - Heading order is meaningful; do not skip levels for visual style
  - Lists (ul/ol/dl) where the content is a list
  - Landmark elements (main, nav, header, footer, aside) over generic div with role
  - Form controls must have programmatically associated labels
  - Do not use placeholder as a substitute for label
  - Button vs link: button for in-page action; a for navigation
validation_checks:
  - landmark/heading/order check via a11y tree
  - label association: <label for> or wrapping <label>
  - button vs anchor usage
  - heading order not skipped
false_positives:
  - "use heading in landmark" on hero section where the visual title does not need a programmatic h1 — review
  - "link looks like button" where a hashed href legitimately navigates — review
anti-patterns:
  - <div onclick> instead of <button>
  - <span role="button"> for a primary action
  - placeholder-only forms
  - cosmetic heading level skips
report_snippets:
  - "Landmarks: header/nav/main/footer present; aside for secondary content"
  - "Form: every control has a programmatically associated <label>"
framework_notes:
  - Single-page apps must still expose landmarks; route changes should update document title and move focus appropriately.
---

# Pack: Platform HTML semantics

Native elements ship with built-in accessibility hooks (role, name, value, default keyboard). Prefer them over generic elements with ARIA bolt-ons. ARIA does not add behaviour; it exposes semantics you still have to implement.

If you write a `<div role="button">`, you must also implement keyboard (Enter/Space), focus, disabled state, and `aria-disabled`. If you write `<button>`, none of that code is yours.

Semantic HTML reduces the audit surface, the CSS surface, and the test surface simultaneously. Treat "can native HTML do this?" as the first question of any markup change.