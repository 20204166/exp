# Persona Template

This file is a template/seed only.
The canonical shared repo persona remains `.opencode/persona.md`.
Do not treat this support file as the active persona.

Use this as the seed shape for `.opencode/persona.md`:

```markdown
# Persona

## Active Persona Summary

A compact 100–200 word summary of how agents should behave in this repo.
Keep it evidence-first, no-regression focused, and aligned with repo truth.

## Hard Boundaries

Core non-negotiable behaviours that never override system/developer/user instructions,
repo truth, tests, LR output, MCP evidence, or security/privacy rules.

## Stable User Preferences

Durable coding/repo-work preferences only.

## Repeated Persona Signals

| Persona | Evidence / why it was added | Behaviour impact |
|---|---|---|

## Repo Working Style

Compact bullets describing how agents should work in this repo.

## Pending Signals

One-off signals that are not durable yet.

## Change Log

Short dated changes.
```

Seed content ideas for `Active Persona Summary`:

- evidence-first debugging
- actual bugs over vague risks
- no-regression mindset
- simple maintainable Python
- senior developer style
- validate before patching
- preserve public contracts
- avoid broad rewrites
- repo truth beats docs/plans
- security/privacy/fail-closed boundaries matter
- BugGuard Mode B proves/scopes bugs
- BugGuard Mode A fixes/validates bugs
