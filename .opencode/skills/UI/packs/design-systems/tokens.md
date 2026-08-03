---
pack: design-systems.tokens
version: 2026-07
authorities:
  - W3C CSS Custom Properties
  - web.dev Design tokens
load_when:
  - design-system cleanup
  - css architecture audit
  - introducing a new visual decision
rules:
  - Tokens encode spacing, colour, radius, shadow, elevation, z-index, typography, motion
  - One source of truth per family (typography, colour, spacing, ...)
  - Naming follows the existing pattern; a new name that does not match is drift
  - Group related tokens (e.g. `--color-bg-default`, `--color-bg-subtle`, `--color-bg-emphasis`)
  - Reuse over mint; mint over duplicate; never duplicate under a different name
validation_checks:
  - duplicate-value check: two tokens with the same value under different names
  - single-use tokens (token created for one call site)
  - orphan tokens referenced nowhere
  - hardcoded values that duplicate an existing token
false_positives:
  - "same value, different name" when names genuinely reflect different intent (review)
anti-patterns:
  - token split ("--space-4" becomes "--space-4-card" + "--space-4-form" with identical values)
  - token sprawl from "future-proofing"
  - tokens for one-off magic numbers
  - tokens re-exported under multiple names without an alias policy
report_snippets:
  - "Tokens: N custom properties; M duplicates / K single-use candidates"
  - "No new tokens introduced in this change plan"
---

# Pack: Design systems — tokens

Tokens are the abstraction that lets a UI change stay consistent without finding every call site. Tokens encode spacing, colour, radius, shadow, elevation, z-index, typography, and motion.

But tokens themselves can drift. A common pattern: a token named `--card-padding` coexists with `--space-4` at the same value. Pick one source of truth. Splitting tokens for "organisation" without an alias policy fragments the system.

Token hygiene wins design-system cleanup more than new tokens. Remove duplicates, name by role, and reserve new tokens for repeated patterns.