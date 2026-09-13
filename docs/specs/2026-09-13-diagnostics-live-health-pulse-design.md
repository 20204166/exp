# Diagnostics Live Health Pulse

## Scope

Refine the existing diagnostics surface in place without changing its data
contract, serialization, refresh ownership, or architectural location. The
work covers the read-only diagnostics projection and its existing presentation
page, using the repository's canonical layout and style owners.

No new component file, support package, dependency, feature workflow, or
business behavior is introduced. Existing explanatory docstrings in
`maintenance/diagnostics.py` remain intact.

## Design Direction

The page uses a **Quiet Operations Console** direction: restrained telemetry
density with editorial hierarchy. It keeps the existing pale indigo base,
white surfaces, charcoal ink, semantic green/amber/red, indigo accent, and
Helvetica type scale. The memorable element is a compact live health pulse at
the top, making active work and failures immediately legible.

The design deliberately avoids gradients, decorative animation, a new visual
language, and changes to diagnostic content.

## Structure

- Retain `maintenance/diagnostics.py` as the read-only projection and JSON
  serialization owner.
- Retain `maintenance/ui/diagnostics_page.py` as the presentation owner.
- Reuse `page_shell`, `section_card`, `metric_row`, `page_status`, spacing
  tokens, fonts, and semantic colors from the existing UI system.
- Extend `maintenance/ui/layout.py` only when a genuinely shared presentation
  mechanism is missing.
- Extend `maintenance/ui/styles.py` with named diagnostics styles/tokens only
  when the existing semantic styles cannot express the required state.

## Behavior

The page will:

- Show a live summary of active work, recent failures, node count, and render
  pressure using values already present in `DiagnosticsSnapshot`.
- Apply state-aware presentation for normal, active, warning/failure,
  unavailable/empty, and disabled states.
- Improve row hierarchy, empty-state clarity, and responsive wrapping while
  retaining every current section and value.
- Continue using the controller's visibility-gated one-second refresh loop.
- Preserve the existing Copy and Back callbacks and the exact serialized
  diagnostics payload.
- Avoid additional timers, fetching, animation, or business logic.

## Consolidation Rules

- Search existing layout and style primitives before creating any helper.
- Share presentation mechanisms, not diagnostic meanings or security rules.
- Keep process, storage, cluster, node, placement, and render interpretations
  separate where their semantics differ.
- Preserve public imports, snapshot fields, serialization fields, callback
  signatures, test seams, and headless widget factories.
- Use guard clauses only where they expose exceptional states without changing
  evaluation order, callback order, lifecycle, or error handling.

## Testing and Evidence

Tests will be added or updated before implementation changes for:

- pulse values and state presentation;
- failure and empty-state wording;
- row reuse during live refresh;
- responsive diagnostic row wrapping;
- existing Copy and Back behavior.

Validation will include focused diagnostics/page tests, affected window/page
tests, the full unittest suite, Ruff lint and formatting, Pyright, Mypy,
`git diff --check`, and the existing `tests/dump_ui.py` render harness. The
desktop and narrow layouts will be inspected from captured before/after UI
evidence; the live Tk resize test will run when a display is available.

## Files

Expected implementation files are the existing owners:

- `maintenance/diagnostics.py`, only if a projection simplification is proven
  useful and API-preserving;
- `maintenance/ui/diagnostics_page.py` for presentation behavior;
- `maintenance/ui/layout.py` and `maintenance/ui/styles.py` only for canonical
  shared presentation mechanisms and tokens;
- related diagnostics tests for behavior coverage.

No runtime source files are expected to be created.
