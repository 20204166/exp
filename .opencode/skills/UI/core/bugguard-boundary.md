# Core — BugGuard Boundary

UI changes live on the presentation surface. BugGuard owns correctness, security, privacy, performance behaviour, and test truth. This file fixes the boundary so a UI task never silently swallows a correctness bug.

## What UI may change

- markup structure for semantics (landmarks, headings, labels, button vs anchor, list semantics)
- CSS (any property, any selector scoped to the touched surface)
- visual component composition (slots, ordering for visual hierarchy, wrapping)
- accessible labels (aria-label, visible labels, error messaging text — *text content only, not validation*)
- non-business interaction affordances (hover/focus/active visuals, modal open/close visual transitions, toast placement)

All of the above are subject to design-language inference and the implementation rules.

## What UI must not own

- validation correctness (field rules, required flags, server validation, error reasons)
- auth / security / session / CSRF / CORS / rate-limit behaviour
- business rules (claim stages, refund thresholds, user-review flow, assisted-submit gating)
- data fetching logic (queries, cache, background jobs, retries)
- performance-sensitive algorithmic changes (query count, N+1, worker load)
- regression test truth (do not change a test to make a UI change pass)

## When UI must hand off

Hand off to BugGuard whenever a UI change exposes or requires a change in any of the above. Do not fix inline; do not implement a UI change that secretly changes behaviour.

Examples:

- A form's error states do not render → UI may fix markup/CSS, but if the error payload itself is wrong or absent, route to BugGuard.
- A modal does not close on outside click → UI may fix the visual/affordance; if the close also skips a cleanup step that the business logic depends on, route to BugGuard.
- A table is slow because of rendering → UI may simplify markup/CSS; if the slowness is a query/load/worker issue, route to BugGuard.
- An accessibility fix requires a new keyboard model on a custom widget → UI may implement the APG keyboard model for the widget; if the widget also drives server state, the server-state side stays with BugGuard.

## Handoff ritual

Record the handoff explicitly in `reports/ui-audit.md` and in the issue row:

```text
Issue UI-NNN
Decision: HAND OFF TO BUGGUARD
Reason: <one sentence, naming the non-UI surface>
Evidence: <paths>
UI-side safe residual (if any): <what UI may still do without touching the BugGuard surface>
```

UI may continue with unrelated issues; it must not silently absorb the BugGuard-owned one.

## Shared surfaces (coordinate, do not overlap)

Some surfaces are jointly owned (e.g. refund document templates: visual styling is UI; the document data and legal copy are BugGuard). For shared surfaces:

- UI proposes the visual/markup change.
- BugGuard owns content/data/validation.
- The change plan explicitly splits UI-owned vs BugGuard-owned rows.

## Strict rules

- Never change a test to make a UI change pass.
- Never change validation rules to make an error state render.
- Never change a route/payload/contract to make a screen look right.
- Never log or print secrets/user data to verify a UI change.
- Never assume "the backend will be fine" — capture the rendered state with synthetic fixtures.

## Relationship to BugGuard skill

This skill does not invoke BugGuard automatically. It recommends a handoff; the user orchestrates the BugGuard run. If BugGuard is already running, this UI skill defers to BugGuard's verdict on any correctness question.