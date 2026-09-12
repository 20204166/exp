# Phase 7 UI Audit

## Scope

Thermals page, shared thermal graph geometry/rendering, dashboard composition,
and dialog composition as exercised by the structural render harness.

## Findings

### Accessibility: threshold state relied on color

`maintenance/ui/thermal_graph.py` rendered warning and critical threshold
lines with the same `(4, 4)` dash pattern. Their only visual distinction was
color. The critical line now uses `(8, 4)`, retaining the existing color and
geometry while adding a non-color distinction.

## Evidence

- Structural render harness: `python -m tests.dump_ui` completed.
- Focused Thermals tests: 16 passed.
- Live Tk resize tests: 8 passed.
- Full Linux suite: 1376 passed.

The harness is structural rather than pixel screenshot evidence. Native
Windows/macOS rendering and screen-reader behavior were not available.
