# Trusted Peer LAN Evidence

## Audit Classification

| Link | Result |
|---|---|
| Target grant provisioner | COMPLETE for normal composition: TLS pairing request, target Tk confirmation, atomic `PeerGrantRecord` save |
| Target listener | COMPLETE: starts during application composition, binds `0.0.0.0`, exposes actual bound port, stops on shutdown, fails soft |
| Advertised endpoint | COMPLETE for new peers: discovery carries actual port, `connectable=true`, and TLS certificate fingerprint only after listener startup |
| Production connector | COMPLETE: `TLSRemoteTransport` plus `AuthenticatedNodeProvider` replaces the no-op manager connector |
| Connection reconciliation | COMPLETE: generation-fenced `CONNECTING`, `ONLINE`, `OFFLINE`, authentication failure, identity change, and bounded retry behavior |
| Credential/grant persistence | COMPLETE and additive: initiator trusted record and target-owned grant persist independently; initiator trust is saved only after target approval |
| Hello and identity validation | COMPLETE: HMAC, request correlation, stable node ID, stable identity fingerprint, and pinned TLS certificate fingerprint are checked |
| Confidentiality | COMPLETE for the production listener: TLS 1.2+ encrypts LAN payloads; HMAC remains the application identity/integrity layer |
| Remote data | COMPLETE for read-only dashboard, component, process-review, and storage-review provider methods; no cleanup or shell operation was added |

## Safety Boundaries Preserved

- Discovery remains presence-only. It never creates trust, credentials, grants, or a selectable operational context.
- Pairing is explicit on the initiator and requires a separate local confirmation on the target.
- Target grants are permission-limited and are checked below the UI by `RemoteService`.
- Replay/freshness checks, request IDs, stable IDs, identity fingerprints, and capability checks remain active.
- Process actions remain target-bound and owned by the existing process-safety implementation; the normal pairing grant is read-only.
- No arbitrary command endpoint, remote file deletion, or generic shell was introduced.

## Evidence

The following are real local TCP/TLS composition tests, not memory-transport tests:

- `tests.test_remote_security`: generated certificate material, restrictive key mode, pinned TLS hello, wrong-certificate rejection, and approved pairing request.
- `tests.test_remote_contract`: existing authenticated read and target-grant contract coverage.
- `tests.test_peer_connection`: connection state, discovery loss, offline transition, and bounded reconnect coverage.
- `tests.test_window_nodes`: normal window composition seams, endpoint hydration, identity mismatch, and pairing failure coverage.

No physical second machine was available in this environment, so this report does
not claim the plan's two-machine A-discovers-B/B-discovers-A evidence. mDNS,
firewall behavior, DHCP address changes, and restart behavior across two installed
applications remain deployment validation items.

## Validation Results

- `python -m unittest discover -s tests -v`: **PASS, 1,149 tests**.
- `./install/build.sh`: **PASS**, version `1.4.7.0`.
- `./install/verify.sh`: **PASS**, 86 wheel members and checksum valid.
- `ruff check .`: **PASS**.
- `ruff format --check .`: **PASS**.
- `pyright`: **PASS**.
- `mypy --ignore-missing-imports maintenance window.py main.py algo.py tests`: **PASS**.
- `mypy --ignore-missing-imports .`: **PASS**, after excluding historical `docs/bug_hunts` evidence from the production Mypy file set.
- `git diff --check`: **PASS**.

## Final Decision

**BLOCKED**

The production listener and read-only connector are composed over real TLS
sockets, but the initial pairing trust ceremony still needs an independently
authenticated or out-of-band trust anchor, and physical two-machine LAN evidence
is unavailable. Destructive remote actions remain outside the normal grant.
