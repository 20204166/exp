# Examples — UI surface reference catalogue

Worked reference artifacts per surface type. Each folder shows a *condensed* run of the UI skill against a representative surface.

| Surface type | Folder | Stack | Mode | Lessons |
|---|---|---|---|---|
| Django form (claims/new) | `django-form-surface/` | Django templates + crispy forms | audit + patch | template inheritance; widget layer; server-rendered states; CSRF-sensitive boundaries |
| React dashboard | `react-dashboard/` | React + CSS Modules | visual polish | component tree slots; CSS Modules composition; composited motion; reduced-motion collapse |
| Tailwind landing page | `tailwind-landing-page/` | Tailwind v4 | responsive fix | arbitrary-value drift; container queries vs media queries; breakpoint tokens |
| Bootstrap admin | `bootstrap-admin/` | Bootstrap 5 | design-system cleanup | Sass vs CSS custom properties; component state classes; dark mode |

## How to use these examples

- They are reference shapes, not finished reports. They illustrate how `surface-map.json`, `design-language.md`, audit issues, opposition findings, and final excerpt should look.
- Real runs produce *more* evidence than these examples. The examples show minimum-credible detail, not minimum-effort.
- Examples are not committed under `.ui/`; they live in the skill folder as static references. Generated `.ui/` artifacts are repo-local per the skill.

Each example contains a `README.md` walkthrough plus:
- `surface-map.json` — conforms to `schemas/surface-map.schema.json`
- `design-language.md` — condensed filled `templates/design-language.md`

A worked opposition finding and final-excerpt appears inside each `README.md` rather than as separate files, so the example stays readable as a single narrative.