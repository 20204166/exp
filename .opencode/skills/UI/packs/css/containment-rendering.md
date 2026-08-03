---
pack: css.containment-rendering
version: 2026-07
authorities:
  - MDN contain
  - MDN content-visibility
  - web.dev Rendering performance
load_when:
  - css architecture audit (performance angle)
  - large list / table surfaces
  - new layout-shift risk
  - heavy shadows / blurs
rules:
  - `contain: layout paint style` constrains a subtree's impact on the rest of the page
  - `content-visibility: auto` skips rendering offscreen subtrees; pair with `contain-intrinsic-size` to avoid layout shift
  - Misuse of containment can break popovers, sticky positioning, and dialogs
  - Perf buys come from avoiding layout/paint/composite work, not from hiding CSS
validation_checks:
  - new `contain` declarations do not break sticky/absolutely-positioned descendants
  - `content-visibility: auto` subtrees have explicit intrinsic size (no CLS)
  - box-shadow / filter / backdrop-filter count is bounded on long lists
false_positives:
  - "layout shift" caused by web font loading, addressed by font-display, not containment
anti-patterns:
  - `contain: strict` on a container with absolutely-positioned descendants the layout depends on
  - `content-visibility: auto` without `contain-intrinsic-size`
  - backdrop-filter on every table row
report_snippets:
  - "Long list: virtualize or content-visibility:auto + contain-intrinsic-size"
framework_notes:
  - Chrome/web.dev treats rendering smoothness as UX; Core Web Vitals include loading, interactivity, visual stability
  - The skill's perf boundary: DOM/fetch/JS-execution semantics are BugGuard territory; perceived paint/composite is UI
---

# Pack: CSS containment and rendering

CSS containment (`contain`, `content-visibility`) lets UI reduce layout/paint/composite cost on large surfaces without changing DOM/data fetching (which is BugGuard territory).

The risk is twofold: a subtree with sticky/absolute descendants depends on its ancestor's containment; misusing `content-visibility` without an intrinsic size causes CLS. Both are perceived-UI risks.

Use this pack for long lists, tables, dashboards with many widgets, and large scrolling surfaces. Do not use it to mask a BugGuard-owned perf problem.