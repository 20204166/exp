# UI Report

## Final report contract

Use this template for the Stage 15 final report. Every section under "Changes made" must answer *what existing token/variant/state/viewport did this change reuse or fix* — never "looks better".

Fill placeholders in `{braces}`. Drop "n/a" rows honestly; do not omit required sections.

---

# UI Report — {surface}

- Mode: {audit only | audit + patch | visual polish | css architecture | responsive fix | accessibility fix | design-system cleanup | component state improvement | full surface refinement | implement design | match screenshot}
- Mode path: {A → C → A style transitions if any; else "-"}
- Risk: {low | medium | high | design-system-altering}
- Evidence level reached: {Tier 0..5}

## 1. Scope
- Surface: {name + slug}
- Files touched: {list}
- Files inspected: {list / "see surface-map.json"}
- Mode: {mode}
- Evidence level: {tier}

## 2. Existing design language inferred
- Typography: {scale from design-language.md}
- Spacing: {rhythm/base unit}
- Colour: {token family + semantic mapping}
- Radius: {language}
- Elevation: {shadow/elevation style}
- Density: {compact/cozy/...}
- Interaction tone: {motion personality}
- Constraints applied: {must_reuse / must_preserve / do_not_introduce highlights}

## 3. Issues found
- Critical: {N} — {ids}
- High: {N}
- Medium: {N}
- Low: {N}
- Deferred: {N}
- Blocked: {N}
- Needs evidence: {N}

(Per-issue detail lives in `ui-audit.json` / `ui-audit.md`.)

## 4. Changes made
For each accepted/modified change:

### Change {id}
- Reason: {one sentence citing the original issue}
- Evidence: {paths in evidence bundle}
- Risk: {low | medium | high}
- Token/variant reused: {name or "none — new, justification below"}
- Justification if new: {one sentence; opposition acceptance on record}
- Validation: {viewport checks, state checks, a11y checks supporting this change}

## 5. Opposition summary
- Accepted: {N}
- Modified: {N}
- Blocked: {N}
- Deferred: {N}
- Needs evidence: {N}
- BugGuard handoff: {N}
- Critic set used: {default | specialist list}
- Opposition file: `reports/ui-opposition-report.md`

## 6. Validation
- Viewport checks: {list of viewport×state captured}
- State checks: {states captured}
- Accessibility checks: {axe + keyboard trace + focus-visible + contrast + reduced-motion}
- Visual diff: {max diff %, regressions outside touched surface: y/n}
- CSS architecture checks: {specificity delta, new !important, new hardcoded values, new global selectors, new dependency}
- Known limitations: {list}

## 7. BugGuard boundary
- Touched correctness logic? {yes/no}
- Touched validation logic? {yes/no}
- Touched performance-sensitive path? {yes/no}
- Needs BugGuard follow-up? {yes/no — list handoff issue ids}

## 8. Remaining recommendations
- Now: {next-safe action}
- Later: {deferred items, with id}
- Do not do: {explicit no-redesign / no-business-logic-touch reminders}

## 9. Commands not run / why
- {command — reason}

## 10. Artifacts
- surface-map.json
- design-language.md
- reports/ui-audit.md
- reports/ui-opposition-report.md
- reports/ui-validation-report.md
- evidence/{screenshots, accessibility, css, traces}/...

## 11. Verdict
- {single-line result}
- Residual risk: {one line}