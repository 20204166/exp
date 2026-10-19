# Expra Connect Backend Migration Design

## Goal

Replace System Analyzer's custom Connect and cluster backend with the reusable
`expra-connect` runtime while preserving the current UI, user-visible behavior,
and persisted trust/cluster information. Do not modify the sibling
`/home/btn17/Downloads/expra-connect` source repository.

## Package source and version policy

Use the newest universal artifact currently available in the local
`expra-connect` distribution directory: `1.9.0.1` (`py3-none-any`). The newer
local `2.2.0.3` wheel is Linux/CPython-3.12-specific and is not suitable for the
app's cross-platform runtime. The configured package index has no
`expra-connect` distribution, so a version pin alone cannot provision target
machines.

The app build/release artifacts will therefore carry the universal dependency
wheel alongside the app wheel. Installers use this local wheel for the
`expra-connect` package itself, while pip may resolve its third-party runtime
dependencies from the configured package index; the missing `expra-connect`
distribution is never fetched from the index. When all dependencies are
already installed, this can complete without downloading them. Declare the
exact runtime version in project metadata and requirements, validate the
companion wheel's name/version/universal tag and checksum during packaging,
and document the supported local source-install path. A later version update
requires a newer universal wheel and an explicit revalidation; do not silently
select a platform-specific artifact.

## Runtime architecture

`expra_connect.ConnectRuntime` becomes the sole owner of peer identity,
discovery, pairing, trust authorization, transport, remote providers, and
cluster operations. The Tk composition root continues to own lifecycle and
inject callbacks. A narrow System Analyzer adapter translates between the
package's headless types and the existing `maintenance.nodes`, scanner, and UI
contracts. Existing pages, wording, selection, confirmation flows, and safe
process/file action boundaries remain in place.

Do not run the existing backend and the package runtime as competing sources
of truth. Migrate in dependency order: first Connect/runtime and its remote
provider paths; then cluster roles, persistence, and UI operations through the
same runtime. Preserve app-owned scanner behavior and bounded SQLite cluster
history/standby storage unless a direct package API replaces a specific
responsibility without changing semantics.

## Persisted state and transition safety

Before cutover, inventory the current `cluster.json`, TLS material, and
package-owned profile/cluster formats. Implement a deterministic one-time
conversion for supported state, including directional trust records, grants,
pairing permissions, cluster IDs, roles, coordinator epoch/lease, invites, and
discovery preference. Validate converted state before activation. Never delete
or overwrite the old state as a migration side effect: retain it as a verified
backup until the new runtime has loaded and saved successfully and acceptance
checks pass. On malformed, unsupported, or partially converted input, fail
closed and preserve the original files for recovery.

TRUST (pairing/records/grants), CLUSTER (membership/roles/epoch), and
CONNECTION (runtime online/offline state) remain independent. Preserve HMAC
authorization, certificate/fingerprint verification, human approval, and
platform-neutral firewall behavior. Never log secrets, private keys, or
fencing-token values, and never show fencing-token values in UI or diagnostics.

## Failure behavior and lifecycle

Runtime startup failure must leave the local dashboard usable and expose an
actionable existing-style offline/unavailable state; it must not infer trust or
membership from discovery. Pairing, persistence, cancellation, and shutdown
failures must preserve the current fail-closed behavior and avoid publishing
uncommitted state. All callbacks that affect widgets must be delivered on the
Tk thread. The runtime must be stopped deterministically when the window
closes.

## Verification and acceptance

- Add adapter and characterization tests before removing old production paths.
- Test package-version selection, wheel metadata/checksum validation, offline
  Linux/Windows installer ordering, and failure rollback using temporary
  directories/artifacts.
- Test state conversion with representative legacy fixtures, including malformed
  and partial input; assert original bytes remain available on migration failure.
- Preserve current UI wiring and all existing behavioral/security contracts in
  unit and integration tests; verify there is one production owner after each
  cutover stage.
- Run repository tests, Ruff, Pyright, and mypy as required by `AGENTS.md`.
- Perform the documented physical two-node acceptance, including Windows as a
  black-box wheel runtime. Automated tests alone must not be described as full
  remote-cluster validation.

## Explicit non-goals

- Replacing or redesigning the UI.
- Modifying/publishing the `expra-connect` source project.
- Upgrading to `2.2.0.3` while it remains available only as a platform-specific
  wheel.
- Removing the legacy state backup before validated migration acceptance.
- Changing local scanning, process termination, file cleanup, or SQLite history
  semantics as unrelated refactoring.
