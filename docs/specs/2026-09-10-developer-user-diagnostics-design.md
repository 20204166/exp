# Developer/User Diagnostics Design

**Status:** Design approved in conversation; implementation not started.

## Goal

Add a lightweight Settings > Diagnostics surface that explains current health,
unavailability, recent failures, active work, peer connection reasons, rejected
results, and component success times without creating a monitoring backend or
persistent telemetry log.

## Scope

This is one integrated feature with four bounded parts:

- Extend existing runtime owners only where a current success/error value is
  missing.
- Project those owners into one immutable diagnostics snapshot.
- Render the snapshot as a themed Settings subpage with visible-page refresh.
- Test and optionally copy/export the bounded snapshot without secrets.

No monitoring service, persistent telemetry, unlimited history, raw exception
exposure, remote diagnostics endpoint, or dashboard-card redesign is included.

## Existing Ownership Map

| Responsibility | Existing owner | Diagnostics use | Decision |
| --- | --- | --- | --- |
| Component schedule, pause, and in-flight state | `ComponentRefreshScheduler` | Component status and active work | Extend existing owner |
| Background operation generation, in-flight state, cached result | `AppCoordinator` | Active keys and generations | Reuse existing owner |
| Component result/failure delivery | `AppWindow` + scheduler/coordinator callbacks | Last success and last error | Extend existing owner at callback boundary |
| Node trust, pairing, capability, and connection state | `NodeContext` / `NodeRegistry` | Node diagnostics | Reuse existing owner |
| Peer failure classification | `maintenance.nodes.classify_peer_failure` | Stable failure category | Reuse existing owner |
| Stale render count and visibility state | `UICoordinator` | Rendering diagnostics | Reuse existing owner |
| Page switching and timer delivery | `PageRouter` / `TimerDelivery` | Settings subpage lifecycle | Reuse existing owner |
| Theme and page primitives | `maintenance/ui/styles.py` and `layout.py` | Consistent UI | Reuse existing owner |

No separate diagnostics registry or generic helper module will be created.

## Non-Goals

- Persisting diagnostic history across launches.
- Retaining lists of errors, events, operations, or stale results.
- Exposing credentials, HMAC secrets, certificate material, request payloads,
  or raw exception objects.
- Adding a monitoring backend, network endpoint, or background telemetry worker.

## Data Model

Create `maintenance/diagnostics.py` as the single normalized projection owner.
Its public records are frozen, slot-based dataclasses. They contain bounded
display values only:

- `ComponentDiagnostic`: key, state, capability, last success time, last error
  category/detail, and whether work is in flight.
- `OperationDiagnostic`: operation key, generation, and in-flight state.
- `NodeDiagnostic`: node ID/display name, trust/pairing state, connection state,
  stable failure reason/detail, and advertised capabilities.
- `RenderDiagnostic`: pending count, request/commit/coalescing counts, and
  stale rejection count from the existing UI coordinator.
- `DiagnosticsSnapshot`: immutable tuples of the records above plus a bounded
  summary of active work, unavailable items, and the most recent failure.

Failure categories use stable wording: `connection_refused`, `timeout`,
`authentication_failed`, `identity_changed`, `unsupported_capability`,
`discovery_unavailable`, `execution_failed`, and `no_data_yet`. Detailed text is
truncated to a fixed limit before entering the snapshot. A serializer emits
plain JSON-safe data from the snapshot; it never serializes arbitrary objects.

The snapshot builder accepts existing owners as dependencies rather than
importing Tkinter or starting work. It reads all registered node contexts,
coordinator states, scheduler state, and UI counters at one composition point.
It does not retain snapshots or add a second cache.

## UI Architecture

Create `maintenance/ui/diagnostics_page.py` as a presentation-only adapter.
It receives a snapshot, callbacks, theme tokens, and injectable widget classes,
following `SettingsHome` and `PreferencesPage` test seams. It renders a compact
summary and expandable/secondary sections for components, operations, nodes,
and rendering. Empty states explicitly say `No data yet`, `Nothing currently
running`, `No recent failures`, or `No remote nodes configured` as applicable.

Add the page to the existing `PageRouter` as a retained Settings subpage. Add
the category in `window_page_data.py`, route it in `window_pages.py`, and build
it using the current page shell, spacing, status colors, fonts, button
coordinator, and selected appearance theme. The page exposes a Back control and
a `Copy diagnostics` action.

## Lifecycle and Integration

`AppWindow` composes the snapshot and supplies it to the page. Diagnostics are
redrawn only while the page is visible, using the existing `TimerDelivery`
path; no worker or new timer service is introduced. The refresh is cancelled
when the page is hidden or the window closes. Existing scan, component,
connection, node-selection, and render callbacks request a lightweight redraw
when the page is visible. Node switching rebuilds from the newly selected
context and cannot display the previous node's state.

The page remains read-only. Copying uses the snapshot serializer and the Tk
clipboard only; it does not write a file or send data over the network.

## State Coverage

The first render with no completed work shows `No data yet` and empty sections.
An in-flight operation shows its operation key and generation. A successful
component shows its last success time. A failed component shows the normalized
category and bounded detail. Unsupported hardware is shown from the existing
`CapabilityState`. Peer states distinguish offline/refused, offline/timeout,
authentication failure, identity change, discovery unavailable, and no data.
Stale render rejections use the existing bounded counter rather than retained
records.

## Testing Plan

Add model/serializer tests for immutable snapshots, truncation, stable failure
categories, empty states, and secret exclusion. Extend coordinator and scheduler
tests for last-success/last-error updates without changing scheduling semantics.
Add node diagnostics tests for every connection and capability state. Add page
tests using recording widgets for summary rows, expanded details, empty states,
copy callbacks, and theme injection. Extend window tests for Settings routing,
visible refresh, cancellation on hide/close, and node switching isolation.

Run the established gates after implementation:

```text
ruff check .
ruff format --check .
pyright
mypy --ignore-missing-imports .
python -m unittest discover -s tests -v
```

## Consolidation Review

Before editing, search all relevant state owners and tests for existing
diagnostic-like fields, failure classification, serialization, page shells,
and refresh timers. Reuse compatible owners and keep specialized meanings
separate. After editing, search again for duplicate tracking. Remaining matches
must be classified as callers, test doubles, platform adapters, or intentional
domain specializations. Any new implementation must have no suitable existing
owner and must live in the narrowest natural module.
