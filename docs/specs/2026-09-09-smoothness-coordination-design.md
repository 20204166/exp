# Smoothness Coordination Design

**Date:** 2026-09-09
**Status:** Approved for implementation planning

## Goal

Improve perceived application smoothness without changing scanner result
contracts, visible refresh intervals, trust decisions, cleanup behavior, or
platform claims.

Success is measured in this order:

1. Tkinter responsiveness during scans, discovery, and page changes.
2. Fast, predictable visible-card freshness.
3. Fewer duplicate scans, stale deliveries, discovery bursts, and refresh
   lifecycle transitions.

## Scope

The work is coordination-first and covers:

- `AppCoordinator` trigger coalescing, generation checks, cached delivery, and
  Tk callback coalescing.
- Visible versus hidden work admission.
- `DiscoverySession` and `NetworkDiscovery` event stabilization.
- Background discovery maintenance and bounded grace windows.
- Developer-only metrics in the existing performance audit reports.
- Failure, cancellation, timeout, shutdown, and stale-result behavior.

It does not add production controls, alter public result shapes, change
scanner accuracy, or rewrite scanner implementations without a separate
measured candidate gate.

## Architecture And Flow

```text
trigger
  -> AppCoordinator coalesces by operation key
  -> visibility/priority gate admits or defers work
  -> scanner/discovery worker runs off Tk
  -> generation check accepts or drops the result
  -> delivery callbacks coalesce onto Tk
  -> visible UI receives one stable update
```

`AppCoordinator` remains the single per-key coordination boundary.
`ComponentRefreshScheduler` remains responsible for interval eligibility.
`DiscoverySession` and `NetworkDiscovery` retain discovery lifecycle and
observation ownership. `AppWindow` remains the composition/controller layer.
Scanner components remain independent of Tk and UI code.

## Coordination Rules

- Repeated triggers for one key collapse into one active operation plus at most
  one pending rerun.
- Cached results may render immediately while a refresh runs in the background.
- Cancelled, stale, or node-invalidated generations never reach the UI.
- Worker completions in one burst may produce one Tk delivery pass.
- Visible work has priority over discovery and hidden-page work.
- Visible refresh intervals remain strict.
- Background discovery work may use a bounded grace window, but its maximum
  staleness must be explicit and cannot suppress authoritative expiry.
- Hidden-page rendering is deferred until the page is visible.

## Discovery Rules

- Add/update events for one peer within the debounce window become one stable
  candidate update.
- A remove followed quickly by an add becomes an update rather than a visible
  disappearance/reappearance.
- TTL expiry remains authoritative and cannot be debounced indefinitely.
- Duplicate unavailable/start failures are coalesced and cannot create retry
  storms.
- Discovery remains best-effort and local-only fallback behavior is unchanged.
- The existing discovery timer owns TTL maintenance; no unbounded worker
  thread is introduced.
- Trust, identity, authorization, and remote action boundaries are untouched.

## Metrics

Developer-only audit output records:

- Tk delivery queue depth and drain duration.
- Worker completions collapsed into one UI delivery.
- Visible versus hidden work admitted, deferred, or dropped.
- Coalesced triggers and pending reruns.
- Cancelled and stale delivery drops.
- Discovery events received versus UI updates emitted.
- Debounce delay and TTL-expiry timing.
- Visible refresh p50/p95 latency.
- CPU and memory impact.

Metrics must not contain user data, credentials, remote process state, file
contents, or cleanup targets.

## State And Failure Coverage

Tests must cover:

- First launch without cached results.
- Visible and hidden pages during active work.
- Repeated triggers, cancellation, timeout, and late completion.
- Cached result while refresh is pending.
- Discovery unavailable, repeated failure, event bursts, and TTL expiry.
- Shutdown with pending workers or deliveries.
- Slow workers while the Tk thread remains responsive.
- Node switching and stale-node result rejection.

Visible pages retain the last valid result during transient failures. First-time
failures retain the existing unavailable state. Shutdown drops pending delivery
safely. Debouncing can delay presentation but cannot suppress trust changes or
authoritative expiry.

## Validation And Rollout

Every candidate follows one gated loop:

1. Capture before metrics for queueing, delivery, discovery bursts, and visible
   versus hidden work.
2. Add focused correctness tests.
3. Implement one coordination or discovery change.
4. Run repository tests and static checks.
5. Repeat interleaved before/after measurements.
6. Retain the change only if responsiveness improves without freshness,
   ordering, cancellation, trust, or shutdown regressions.

Rollout order:

1. Add developer-only metrics.
2. Improve `AppCoordinator` delivery coalescing.
3. Stabilize discovery event presentation.
4. Verify hidden-work deferral and visible priority.
5. Consider scheduler changes only if evidence still shows a smoothness issue.

## Non-Goals

- New production preferences or controls.
- Removing the process sampling wait without an explicit accuracy decision.
- Suppressing discovery expiry, trust changes, or security-relevant events.
- Cross-platform performance claims from simulated adapters.
- Broad scanner rewrites or unmeasured caching.
