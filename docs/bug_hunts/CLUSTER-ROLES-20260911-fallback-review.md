# Cluster Roles Fallback Assurance Review

Date: 2026-09-11

## Evidence

- Repository truth: role state is pure in `maintenance/components/cluster_roles.py`;
  persistence remains owned by `ClusterStore`; authenticated role operations are
  allowlisted in `maintenance/remote.py`; bounded storage is isolated in
  `maintenance/components/cluster_storage.py`; target safety remains in the
  existing action backends.
- Fresh tests: `tests.test_cluster_roles`,
  `tests.test_cluster_roles_persistence`, `tests.test_cluster_storage`, and
  `tests.test_cluster_adversarial` cover coordinator/worker constraints,
  stale fencing, return fencing, invite expiry, legacy state, duplicate batches,
  age/size caps, stale role messages, and oversized role payload boundaries.
- Compatibility tests: existing cluster, remote security, peer connection,
  window, node, diagnostics, UI, and package-structure suites pass.

## Official References

- Python `sqlite3`: https://docs.python.org/3/library/sqlite3.html
  confirms parameter binding, explicit commit behavior, and timeout handling for
  locked tables. The adapter uses placeholders, short transactions, and a busy
  timeout.
- SQLite WAL: https://sqlite.org/wal.html
  confirms WAL is local-host only, has one writer, and may produce `SQLITE_BUSY`.
  The implementation does not use a network-mounted database and treats locked
  and I/O failures as bounded storage degradation.
- Python HMAC: https://docs.python.org/3/library/hmac.html
  recommends `compare_digest` for supplied digest comparison; the existing
  envelope verifier and role fencing checks use it.

## Residual Risk

| Area | Evidence | Residual risk |
| --- | --- | --- |
| Runtime failover wiring | Pure promotion and peer heartbeat primitives are tested | Full multi-installation failover needs platform/runtime integration testing |
| SQLite physical disk cap | Logical encoded batch cap is enforced | SQLite journal/WAL physical bytes can exceed logical payload bytes |
| Pairing role grant | Role UI and typed operations are bounded | Existing pairing grants intentionally remain read-only; deployment must provision coordinator control authority separately |
| Cross-platform runtime | Import, compile, and Linux tests pass | Native macOS/Windows listener and filesystem behavior were not available |
| Review topology | Fallback review performed in this runtime | Agent 5 and four BugGuard subagents were unavailable; no claim is made that they reviewed this change |
