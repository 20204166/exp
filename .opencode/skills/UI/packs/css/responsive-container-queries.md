---
pack: css.responsive-container-queries
version: 2026-07
authorities:
  - MDN Media queries
  - MDN Container queries
  - web.dev Responsive design
load_when:
  - responsive fix
  - component placed in narrow sidebar / modal / card / table cell / split pane
  - layout audit
rules:
  - Media queries vary by viewport; container queries vary by nearest container ancestor
  - Container queries exist specifically because component layout often depends on container size, not viewport
  - Annotate container ancestors with `container-type: inline-size` (and a name where needed)
  - Do not replace all media queries with container queries — global layout still uses viewport
  - Breakpoint values come from the project's token system; do not invent new ones
validation_checks:
  - the touched component's layout varies correctly with its container, not just viewport
  - no horizontal scroll at smallest target container width
  - no overflow clipping at narrow containers
  - modals/sidebars tested at both compact and wide containers
false_positives:
  - "media query needed" when the real determinant is container width (use cq)
  - "container query needed" when viewport rules already work (global layout)
anti-patterns:
  - arbitrary-value media queries (`@media (min-width: 723px)`)
  - mixing two responsive mechanisms without resolution order (e.g. tailwind responsive variants AND custom media queries that disagree)
  - breaking point chosen by one screen's broken look
report_snippets:
  - "Responsive: breakpoints from token scale (sm/md/lg/xl); container queries used for sidebar/modal/table-cell placement"
framework_notes:
  - Tailwind has container-query variants (`@sm:` etc.); use them instead of raw media queries when the project is utility-first
  - Bootstrap breakpoints (sm/md/lg/xl/xxl) are Sass variables; reuse project overrides, do not hardcode
---

# Pack: Responsive / container queries

Responsive layout is not just "mobile and desktop". The default viewport matrix is 320/375/390/414/768/1024/1280/1440/wide-desktop; narrow to project targets.

Two mechanisms:

- **media queries** vary by viewport; good for app shell, grid, container widths
- **container queries** vary by the nearest container ancestor; good for components that live in narrow sidebars, cards, modals, table cells, split panes

A component placed in a 300px card should not rely on a 1024px viewport rule. Use container queries there.

Breakpoint values come from tokens (Tailwind theme / Bootstrap Sass vars / CSS custom properties). Inventing a `@media (min-width: 723px)` to fix one broken view is anti-pattern.