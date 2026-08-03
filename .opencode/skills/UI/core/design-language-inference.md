# Core — Design-Language Inference

Stage 3. **Mandatory.** Never skip this stage before proposing visual changes. This stage is the main defence against generic AI UI.

The reason: without inferring the existing design language, an implementation will introduce random gradients, new shadows, inconsistent button styles, modernised cards, arbitrary border radii, and "clean SaaS dashboard" aesthetics that drift the product.

## What to infer

Before suggesting any visual change, answer:

- What design system already exists?
- What visual decisions are intentional?
- What inconsistencies are real defects vs intentional density/tone?
- What looks "ugly" but is actually consistent with the product?
- What should not be changed?

## Inference dimensions

For the audited surface, infer:

- **brand tone** — utility/admin/enterprise vs marketing/consumer
- **density** — compact, cozy, comfortable, airy
- **spacing rhythm** — base unit (4px/8px), scale usage
- **type scale** — sizes, weights, line heights, families
- **colour usage** — semantic colours (success/warn/error/info), neutrals, accent
- **border radius language** — sharp, soft, pill, mixed
- **shadow / elevation style** — flat, light, layered, none
- **icon style** — outline, solid, duotone, illustrated, none
- **component conventions** — card chrome, table density, form control style
- **button hierarchy** — primary/secondary/tertiary styles, ghost/text variants
- **form style** — label position, error placement, control density
- **empty / loading / error state style** — skeleton, spinner, illustration, copy
- **layout grid** — columns, gutters, container widths, breakpoints
- **animation personality** — none, functional transitions, motion-heavy, playful

Write the result to `.ui/<surface-slug>/design-language.md` using `templates/design-language.md`. This artifact constrains every later stage.

## Token inventory (part of inference)

Detect sources of truth:

- CSS custom properties (`:root` and per-component)
- Tailwind theme values (`tailwind.config.*`)
- Bootstrap variables (`_variables.scss` / CSS custom properties)
- SCSS variables (`$var`)
- CSS Modules conventions (`composes`, scoped exports)
- design-system token files
- hardcoded magic values (the anti-pattern)
- duplicate colours / duplicate spacing values

Record under `token-inventory.json` (optional artifact) and summarise in `design-language.md`.

## Constraints to emit

The inference must produce explicit constraints in `design-language.md`:

```text
constraints:
  - must_reuse: ["--space-4", "--color-text-primary", "--radius-md"]
  - must_preserve: ["compact admin density", "8px spacing rhythm", "primary button hierarchy"]
  - do_not_introduce: ["new shadows", "new gradients", "glassmorphism", "new colour palette"]
  - spa_or_marketing_only: ["28px padding", "large hero shadows"]
```

`do_not_introduce` loads `packs/anti-patterns/generic-ai-ui.md` defaults by default. Widen it only when the product's existing language genuinely contains the pattern.

## Inference evidence

Every inference row must cite evidence:

```text
density: compact
evidence: ["static/css/app.css:--space-2 = 0.5rem on surfaces", "screenshot: dashboard-default-1280 shows 8px row gaps"]
```

Without evidence, the inference is Speculative confidence and may not constrain implementation. If inference cannot rise above Speculative for a dimension, record that gap — do not default to a generic aesthetic.

## Governing rule

```text
Do not introduce a new visual language unless explicitly requested.
```

"Explicitly requested" means the user named the change ("redesign the empty state", "introduce dark mode", "switch to rounded cards"). A vague "make it look better" is not a request for a new visual language; it is a request to polish within the existing one.

## Tie-breaking

When inference and a user instruction conflict:

- explicit user instruction wins for scope (what to touch)
- inferred design language wins for gram (how it should look), unless the user explicitly asks for a new language

If the user asks for a genuinely new visual language, this stage still runs to record what changes against the baseline. Redesign tasks still require a "before" snapshot of the existing language for the report.