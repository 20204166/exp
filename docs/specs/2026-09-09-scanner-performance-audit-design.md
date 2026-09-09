# Scanner Performance Audit Design

**Date:** 2026-09-09
**Status:** Approved for implementation planning

## Goal

Create a full performance audit and optimization loop for the application's
scanner surface and `AppCoordinator`. The work must measure real costs first,
write only controlled evidence-backed changes initially, and expand to broader
optimizations only after the measurement and validation process has proved
reliable.

The audit covers both interactive dashboard refreshes and all public scanner
APIs. Success is evaluated using latency, resource usage, and reproducible
safety evidence.

## Scope

The audit covers:

- Dashboard orchestration and component coordination.
- `AppCoordinator` coalescing, cache retrieval, freshness, cancellation,
  retries, worker lifecycle, Tk delivery, and stale-result rejection.
- CPU, memory, disk, and process sampling.
- GPU detection, NVML success/failure paths, and platform fallbacks.
- Temperature collection and telemetry updates.
- Network counters and local discovery lifecycle.
- Downloads scanning, hashing, duplicate detection, and cache reuse.
- Background task delivery, cancellation, timeout, and retry behavior.

It covers cold and warm scans, repeated unavailable probes, concurrent and
coalesced requests, cancellation during expensive work, timeout and late
completion, and empty, large, and representative synthetic inputs.

The audit does not assume that every candidate should be changed. A candidate
is selected only when its cost is reproducible, attributable, and compatible
with the application's explicit freshness, cancellation, fallback, and
user-visible behavior contracts.

## Architecture

The audit is organized into four layers:

1. **Workload layer** exercises public scanner and coordinator APIs across the
   scenarios in the scope.
2. **Measurement layer** records timing distributions, CPU time, peak memory
   where available, subprocess executions, filesystem/network activity, and
   cache state.
3. **Platform-adapter layer** runs native probes where available and uses
   deterministic injected fakes for Windows and macOS branches that are not
   available on the current host.
4. **Evidence layer** normalizes results, ranks hotspots, and creates a
   candidate record or a Mode C BugGuard evidence packet.

The data flow is:

```text
workload -> scanner/coordinator seam -> measurement record
         -> normalized report -> candidate decision
         -> controlled code change -> repeat measurement and validation
```

The initial harness observes behavior externally or through existing injected
seams. It must not change scanner behavior, refresh policy, cache policy, or
user-visible output merely to collect measurements.

Scanner execution cost and coordination cost are recorded separately. This
avoids optimizing a probe while overlooking queueing, cache lookup, worker,
coalescing, or Tk delivery overhead in `AppCoordinator`.

## Platform Evidence

Native Linux measurements are collected where the host supports them. Windows
and macOS branches are exercised with injected deterministic fakes when those
platforms are unavailable. Every result labels its evidence as native,
simulated, or unavailable; simulated results are not presented as equivalent
to native measurements.

## Measurement Rules

Each workload records:

- Workload and scenario name.
- Platform and optional-dependency availability.
- Scanner and coordinator path exercised.
- Input fixture profile.
- Cold, warm, and cache state.
- Repetition count and distribution statistics.
- CPU, memory, subprocess, filesystem, and network counters where available.
- Error, fallback, cancellation, and timeout behavior.
- Native, simulated, or unavailable evidence classification.

Measurements use repeated interleaved runs. Reports include median, p95,
quartiles, and outliers; a single mean is not sufficient evidence. Cold-start
costs are separated from steady-state costs. Dashboard impact ranks candidates
ahead of component impact only when evidence quality is otherwise comparable.

## Read-Write Optimization Loop

The implementation proceeds in gated phases:

1. Build the read-write-capable benchmark and measurement harness while
   keeping application behavior unchanged.
2. Audit all scanner and `AppCoordinator` paths and produce ranked findings.
3. Implement only low-risk, evidence-backed optimizations first. These may
   include bounded caches, repeated-failure suppression, safe coalescing, or
   deferred work when existing compatibility and freshness contracts remain
   explicit.
4. Re-run interleaved before/after measurements and all validation gates for
   each change.
5. Expand the change scope only after the first candidates prove the harness,
   measurements, and review process. Broader changes may include
   cross-component scheduling, coordinator policy improvements, or bounded
   freshness changes, but require additional contract and stale-data analysis.

A candidate is stopped and retained as an audit finding when it is not
   reproducible, changes behavior unexpectedly, weakens cancellation or
   fallback guarantees, serves data beyond its allowed freshness, or fails to
   meet the agreed latency/resource criteria.

## Error And Failure Handling

Failure paths are measured as performance surfaces, including missing optional
dependencies, permission errors, inaccessible files, failed subprocesses,
NVML initialization failures, unavailable discovery, cancellation, timeout,
coordinator retry, late worker completion, and Tk delivery after shutdown.

Benchmark failures are classified as expected unavailable-path results,
harness failures, or application defects. Diagnostic failures must not be
hidden or converted into user-visible behavior changes by the audit.

## Candidate Evidence

The audit produces:

- Machine-readable benchmark results.
- A human-readable ranked audit report.
- A candidate register with `confirmed`, `noise`, `not actionable`, or
  `requires design` status.
- A separate Mode C BugGuard evidence packet for every implemented candidate.

Each implemented candidate must include a focused regression test and a
counter-test. Its evidence packet must cover reproduction, repository-truth
contracts, architecture and security impact, before/after measurements,
cache/freshness analysis, and opposition review.

## Validation Gates

- Existing repository tests pass before and after each benchmark or code
  change.
- `ruff check .` passes.
- `ruff format --check .` passes.
- Pyright and `mypy --ignore-missing-imports` pass for the relevant application
  and test scope.
- Platform seams are deterministic where injected fakes are used.
- Native and simulated evidence remain clearly distinguished.
- Interleaved measurements report median, p95, quartiles, and outliers.
- Cancellation, timeout, coalescing, stale-result, and late-completion tests
  cover coordinator changes.
- No optimization proceeds without its Mode C BugGuard evidence packet.

## Non-Goals

- A blind rewrite of all scanners.
- Claiming cross-platform performance from one host or from simulated probes.
- Changing user-visible refresh behavior without an explicit freshness design.
- Treating one noisy benchmark run as proof of a performance win.
- Combining unrelated optimizations into one unreviewable patch.
