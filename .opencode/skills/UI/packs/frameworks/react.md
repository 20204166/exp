---
pack: frameworks.react
version: 2026-07
authorities:
  - React docs
  - MDN accessibility for React
load_when:
  - react detection
rules:
  - Surface comprises component tree + props/state + slots; CSS lives in CSS Modules / CSS-in-JS / Tailwind / vanilla
  - State lives in component state, props, URL, or store; do not move state for a visual change
  - Component composition is the UI surface; do not refactor component boundaries for visual reasons
validation_checks:
  - component slot children mapped in surface-map
  - state matrix: how each state renders (no reveal from props mutation alone)
  - styles attached via the project's chosen CSS approach
false_positives:
  - "missing hover" issue on a state driven by external store above the rendered component — may require checking a parent
anti-patterns:
  - inline style={{} } for repeated visual values (tokenize)
  - styled-components via template string that hides the resulting class
  - state hoisting only to add a hover prop
framework_notes:
  - Storybook stories are evidence surfaces for state matrix — capture them
  - CSS-in-JS adds runtime classes; the perf boundary to BugGuard is when CSS-in-JS changes render/DOM semantics
---

# Pack: React

React couples components and state. A UI change in React is not a free CSS replacement: it can touch component composition, props, states, slots, and stores.

Surface discovery for React maps the component tree, props/state, slots, and the chosen styling approach (CSS Modules / CSS-in-JS / Tailwind / styled-components / vanilla). Component-level state machine maps to the state matrix required at Stage 4.

Do not refactor component boundaries for visual reasons. If a visual change requires splitting a component, that is architecture work — record it in the change plan and consider whether some of it is BugGuard owned (if business logic is entangled).