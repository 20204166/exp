# UI Skill — file catalogue

This skill treats UI quality as a rendered-surface evidence system with design-language preservation, not a multi-agent debate.

Entry point: `SKILL.md` (uppercase to match the repo's skill-loading convention; the architecture spec named it `skill.md`).

## Folder map

| Path | Role |
|---|---|
| `SKILL.md` | Registered skill entry, frontmatter, non-negotiable rules, modes, 16-stage workflow |
| `README.md` | This catalogue |
| `core/` | One file per pipeline stage / cross-cutting rule (orchestrator, discovery, evidence, design-language, audit taxonomy, implementation, validation, opposition, bugguard boundary) |
| `packs/` | Versioned, queryable research packs — load only the ones a surface needs |
| `schemas/` | JSON schemas for `surface-map`, `design-language`, `ui-audit`, `opposition`, `validation` |
| `templates/` | Report/plan templates: ui-report, ui-opposition-report, ui-change-plan, design-language |
| `adapters/` | Per-stack notes: how surface discovery/evidence/validation differ for React/Vue/Jinja/Django/Flask/FastAPI/Tailwind/Bootstrap/vanilla CSS/CSS Modules/SCSS |
| `examples/` | Reference artifacts per surface type: django-form-surface, react-dashboard, tailwind-landing-page, bootstrap-admin |

## core/ files

| File | Stage it owns |
|---|---|
| `orchestrator.md` | Stage 0 request classification + routing + mode transitions + final synthesis |
| `surface-discovery.md` | Stage 1 surface-map build |
| `evidence-model.md` | Stage 4 evidence capture + tiers + hallucination guards |
| `design-language-inference.md` | Stage 3 mandatory design-language extraction |
| `audit-taxonomy.md` | Stage 6 typed audit modes + issue schema + visual-debt taxonomy + severity |
| `implementation-rules.md` | Stage 11 patch rules + CSS change hierarchy + UI budget |
| `validation-rules.md` | Stages 12/13/14 layered validation (static/render/a11y/interaction/perf) |
| `opposition-rules.md` | Stage 9 deterministic opposition checklist + decisions |
| `bugguard-boundary.md` | Boundary between UI-owned and BugGuard-owned changes |

## packs/ catalogue

| Pack id | Path |
|---|---|
| 00-platform-html-semantics | `packs/accessibility/semantic-html.md` |
| 01-wcag-22-accessibility | `packs/accessibility/wcag-22.md` |
| 02-aria-apg-widgets | `packs/accessibility/aria-apg-widgets.md` |
| 03-css-cascade-specificity-layers | `packs/css/cascade-layers.md` |
| 04-css-custom-properties-design-tokens | `packs/css/custom-properties-tokens.md` |
| 05-responsive-media-container-queries | `packs/css/responsive-container-queries.md` |
| (specificity) | `packs/css/specificity.md` |
| (containment-rendering) | `packs/css/containment-rendering.md` |
| 07-typography-readability-density | `packs/design-systems/typography.md` |
| (spacing) | `packs/design-systems/spacing.md` |
| (colour) | `packs/design-systems/colour.md` |
| (tokens) | `packs/design-systems/tokens.md` |
| (component-anatomy) | `packs/design-systems/component-anatomy.md` |
| (motion) | `packs/design-systems/motion.md` |
| 12-design-system-component-anatomy | (covered by `design-systems/component-anatomy.md`) |
| 15-data-tables-dashboard-density | (covered within `audit-taxonomy.md` mode guidance + `design-systems/spacing.md`) |
| 16-framework-react | `packs/frameworks/react.md` |
| 17-framework-vue | `packs/frameworks/vue.md` |
| 18-framework-jinja-django-flask-fastapi | `packs/frameworks/jinja-django-flask-fastapi.md` |
| 19-tailwind | `packs/frameworks/tailwind.md` |
| 20-bootstrap | `packs/frameworks/bootstrap.md` |
| 21-css-modules-scss | `packs/frameworks/css-modules.md`, `packs/frameworks/scss.md` |
| 22-visual-regression-testing | `packs/validation/visual-regression.md` |
| 23-storybook-component-testing | (referenced from `packs/validation/visual-regression.md`) |
| 24-anti-generic-ai-ui | `packs/anti-patterns/generic-ai-ui.md` |
| (unsafe-redesign) | `packs/anti-patterns/unsafe-redesign.md` |
| (css-override-hacks) | `packs/anti-patterns/css-override-hacks.md` |
| 06-layout-grid-flex-positioning | (covered within `packs/css/responsive-container-queries.md` + `design-systems/spacing.md`) |
| 08-colour-contrast-theming-dark-mode | `packs/design-systems/colour.md` |
| 09-motion-interaction-feedback | `packs/design-systems/motion.md` |
| 10-browser-rendering-paint-composite | `packs/css/containment-rendering.md` |
| 11-css-performance-containment | `packs/css/containment-rendering.md` |
| 13-forms-errors-validation-states | (covered by `audit-taxonomy.md` component-state mode) |
| 14-navigation-information-architecture | (covered by `audit-taxonomy.md`) |
| 25-production-ui-reporting | `templates/ui-report.md` |

Packs are small, versioned, queryable rule packs — not essays. Each pack declares `load_when`, `authorities`, `rules`, `anti-patterns`, `validation_checks`, `false_positives`, `framework_notes`, and `report_snippets`.

## Routing quick-reference

See `core/orchestrator.md` for the full router. Short version:

| Request | Required |
|---|---|
| "make this look better" | design-language inference + visual polish audit |
| "fix responsive layout" | responsive pack + viewport matrix |
| "clean CSS" | CSS architecture pack + token inventory |
| "make accessible" | WCAG/APG/semantic HTML packs + keyboard validation |
| "improve component" | component-state matrix + design-system pack |
| "audit whole UI" | surface discovery + sampling strategy + full report |
| "implement this design" | design-language compatibility + visual validation |
| "match screenshot" | screenshot evidence + visual diff + anti-hallucination rules |

## Generated artifacts

See `SKILL.md` "Generated project artifacts". Required: `surface-map.json`, `design-language.md`, `reports/ui-audit.md`, `reports/ui-opposition-report.md`, `reports/ui-validation-report.md`. Optional artifacts listed in `SKILL.md`.

## Schemas

JSON schemas in `schemas/` define the machine-readable shape of `surface-map`, `design-language`, `ui-audit`, `opposition`, and `validation`. Templates in `templates/` define the human-readable shape.