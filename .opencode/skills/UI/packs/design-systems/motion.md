---
pack: design-systems.motion
version: 2026-07
authorities:
  - W3C prefers-reduced-motion (WCAG 2.3.3)
  - MDN CSS transitions/animations
  - Nielsen Norman Group microinteractions
load_when:
  - visual polish adding animation
  - interaction audit
  - introducing/removing a transition
rules:
  - Every motion change must respect `prefers-reduced-motion`
  - Microinteraction = trigger -> narrowly targeted feedback, not decoration
  - Transitions on composited properties (transform, opacity) over layout properties
  - Duration + easing from token system; no magic numbers
  - Reduced-motion fallback: essential motion that conveys state still allowed; decorative motion removed
validation_checks:
  - reduced-motion: decorative transitions collapse to instant
  - no long main-thread animation (>150ms on layout properties is suspect)
  - durations from tokens (duration-fast/normal/slow)
  - microinteraction pairs a clear trigger with deterministic feedback
false_positives:
  - "missing animation" where none was present and none is required
anti-patterns:
  - hover-scale that adds a shadow without reduced-motion fallback
  - large spinners over invisible skeleton states
  - staggered list entrance with no trigger hierarchy
report_snippets:
  - "Motion: durations from token scale; reduced-motion collapses to 0ms"
framework_notes:
  - Per NNGroup, microinteractions are organized around a trigger and narrowly targeted feedback; judge them as pairs
---

# Pack: Design systems — motion

Motion is the most visible part of UI polish and the easiest to overdo. Treat it as trigger—feedback pairing, not as decoration.

`prefers-reduced-motion` is mandatory for every change that adds motion. Even essential state-conveying motion (e.g. a confirmation checkmark) must collapse to a no-motion variant for reduced-motion users, while preserving the semantic.

Duration and easing come from tokens. A magic `transition: all 0.23s` is the same flavour of debt as a magic `padding: 13px`. Composited properties (`transform`, `opacity`) over layout properties (`width`, `top`, `left`) for jank-free motion.