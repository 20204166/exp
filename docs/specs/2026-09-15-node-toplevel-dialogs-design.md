# Node Toplevel Dialogs Design

**Status:** Approved design
**Date:** 2026-09-15

## Goal

Add four seamless, secondary-window workflows for node connections, pairing,
node details, and dashboard sharing without changing existing node models,
background work, authorization, persistence, or page navigation.

## Scope

The existing Nodes and Cluster pages remain in the main `Tk` window. Their
actions open focused `Toplevel` dialogs. The four workflows are:

1. Add/test a manual node connection.
2. Confirm pairing and trust for a discovered node.
3. Inspect a node's identity and operational details.
4. Confirm or stop read-only dashboard sharing.

## Architecture

Add presentation-only dialog adapters under `maintenance/ui/`. Each receives
immutable display data and dependency-style callbacks. Dialogs do not import
registries, transports, scanners, persistence, or coordinator internals.

`AppWindow` remains the composition root and owns one dialog instance per
workflow. Existing callbacks remain authoritative: manual-host registration,
connection testing, pairing, node administration, and dashboard sharing are
not duplicated. Existing background/coordinator paths deliver results on the
single Tk thread.

## Behavior

### Connection

Collect host, optional port, and display name. Validate locally, then delegate
test and add operations to the existing callbacks. Keep the dialog open for
validation or operation errors.

### Pairing

Show hostname, stable node ID, identity fingerprint, and TLS fingerprint.
Require explicit confirmation, then delegate to the existing pair callback.
The dialog never grants trust or permissions itself.

### Node details

Show read-only identity, host, port, pairing state, connection state, role, and
permissions. Any action button delegates to an existing callback and is shown
only when allowed by the supplied node specification.

### Sharing

Show current sharing state and the existing supported five-minute duration.
Confirm delegates to the current sharing callback. When sharing is active,
offer the existing stop-sharing action instead of creating a new state model.

## Lifecycle and Safety

Each dialog is transient to the main window, has one close path, and is
idempotent so repeated clicks do not create duplicate windows. Closing never
cancels unrelated scans or node operations. Destruction clears its controller
reference. Widget updates from delayed callbacks check that the dialog still
exists. Page refreshes use existing Nodes/Cluster refresh methods.

## Testing

Headless widget fakes cover construction, callback payloads, local validation,
close behavior, and action visibility. Controller tests cover dialog routing
and callback preservation. Existing node, coordinator, pairing, permission,
sharing, and background tests remain unchanged.

Validation uses focused tests, the full repository test command, `ruff check .`,
`ruff format --check .`, `pyright`, and `mypy --ignore-missing-imports`.

## Explicit Non-Goals

- No second `Tk()` root or second event loop.
- No new worker, scanner, transport, authorization, or persistence layer.
- No removal of existing page state or background refresh behavior.
- No wheel rebuild as part of implementation.
