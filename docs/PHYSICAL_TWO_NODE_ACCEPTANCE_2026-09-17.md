# Physical Two-Node End-to-End Acceptance + Failure-Injection Audit

**Date:** 2026-09-17  
**App version:** 1.6.0.4  
**Status:** RUNBOOK ONLY — no physical evidence recorded yet

> **Scope:** This document is the authoritative acceptance runbook for the remote-cluster
> feature of System Analyzer.  It covers discovery, pairing, connection-state observability,
> cluster join, role mutation, dashboard sharing, lease propagation, failover, revocation,
> and associated failure modes.  It does NOT constitute a passed validation until the
> Observed and Evidence columns are filled in from a real two-machine test run.
>
> **Do NOT say "remote cluster is fully validated" because automated unit tests pass.**
> Unit tests exercise individual components in isolation.  This runbook exercises the
> real network stack, real TLS handshakes, real mDNS advertisements, and real wall-clock
> timing.

---

## Table of Contents

1. [Canonical Machines](#1-canonical-machines)
2. [Security Constraints](#2-security-constraints)
3. [Isolation Setup](#3-isolation-setup)
4. [State File Inventory](#4-state-file-inventory)
5. [Safe Backup Procedure](#5-safe-backup-procedure)
6. [Baseline Capture](#6-baseline-capture)
7. [Scenario Format](#7-scenario-format)
8. [Failure Classification Taxonomy](#8-failure-classification-taxonomy)
9. [Scenarios SC-01 through SC-55](#9-scenarios)
10. [Post-Run Checklist](#10-post-run-checklist)
11. [Log Review Checklist](#11-log-review-checklist)
12. [Persistence Review Checklist](#12-persistence-review-checklist)
13. [Automated Regression Gate](#13-automated-regression-gate)

---

## 1. Canonical Machines

| Role during test | Label | Notes |
|---|---|---|
| Initial Coordinator | **NODE A** | Runs the cluster; creates invites |
| Initial independent node | **NODE B** | Later joins as Worker, then Subcoordinator |

Either machine may run any OS supported by the app.  Both must be on the same LAN subnet
for mDNS discovery.  Cross-subnet scenarios (VPN/firewall) are covered in SC-48–SC-49.

---

## 2. Security Constraints

These constraints apply to EVERY step in this runbook.  Violation invalidates the run.

- **Never commit secrets** to the repository.
- **Never log or record**: HMAC secrets; TLS private key material; raw fencing token values.
  Fencing token *presence* (yes/no) may be recorded.
- **Never expose** the fencing token in user-visible evidence fields below.
- **Do NOT blindly delete user state.**  Use isolated test profiles (§3).
- **Do not weaken security/firewall configuration** automatically or as part of setup.
- Evidence screenshots/pastes that inadvertently capture a secret must be redacted before
  being committed or shared.

---

## 3. Isolation Setup

Both machines must use isolated config profiles so test state does not contaminate real
user data.  The app reads config root from `XDG_CONFIG_HOME` on Linux.

### 3.1 Linux isolation

```bash
# Choose a throwaway path for this test run.
export SA_TEST_ROOT="$HOME/sa-physical-test-2026-09-17"
mkdir -p "$SA_TEST_ROOT"

# Launch a completely isolated instance:
XDG_CONFIG_HOME="$SA_TEST_ROOT" python main.py
```

All state files will land under `$SA_TEST_ROOT/system-analyzer/`.

### 3.2 macOS isolation

```bash
export SA_TEST_ROOT="$HOME/sa-physical-test-2026-09-17"
mkdir -p "$SA_TEST_ROOT"
HOME="$SA_TEST_ROOT" python main.py
```

### 3.3 Windows isolation

```bat
set SA_TEST_ROOT=%USERPROFILE%\sa-physical-test-2026-09-17
mkdir "%SA_TEST_ROOT%"
set APPDATA=%SA_TEST_ROOT%
python main.py
```

### 3.4 Verification

After first launch (before any pairing), confirm isolation:

```bash
ls "$SA_TEST_ROOT/system-analyzer/"
# Expected files: cluster.json  preferences.json  peer-tls.crt  peer-tls.key
```

If those files appear under `$SA_TEST_ROOT` and NOT under `~/.config/system-analyzer/`,
isolation is confirmed.

---

## 4. State File Inventory

All files live under `$XDG_CONFIG_HOME/system-analyzer/` (Linux) or equivalent.

| File | Purpose | Created when |
|---|---|---|
| `cluster.json` | Cluster membership, trusted nodes, epoch, roles | First launch |
| `preferences.json` | User preferences (display name, colors) | First launch |
| `peer-tls.crt` | Node's TLS certificate (public) | First launch |
| `peer-tls.key` | Node's TLS private key | First launch |
| `cluster-history.sqlite3` | Audit log of cluster events | First cluster join |
| `cluster-standby.sqlite3` | Standby state for failover | First cluster join |

**Never paste the contents of `peer-tls.key` into evidence.**

---

## 5. Safe Backup Procedure

Before each scenario that modifies persistent state, back up the test profile:

```bash
cp -a "$SA_TEST_ROOT/system-analyzer" \
      "$SA_TEST_ROOT/system-analyzer.bak.$(date +%H%M%S)"
```

To restore:

```bash
rm -rf "$SA_TEST_ROOT/system-analyzer"
cp -a "$SA_TEST_ROOT/system-analyzer.bak.HHMMSS" \
      "$SA_TEST_ROOT/system-analyzer"
```

---

## 6. Baseline Capture

Record the following for BOTH nodes BEFORE any pairing or cluster operations.
Fill in the Observed column from the app's UI and/or `cluster.json`.

| Field | NODE A observed | NODE B observed |
|---|---|---|
| App version (Help → About or `_version.py`) | | |
| Node ID (from `cluster.json` `.node_id`) | | |
| Display name (Preferences → Node Name) | | |
| Cluster ID (from `cluster.json` `.cluster_id`) | | |
| Role (from `cluster.json` `.role`) | | |
| Epoch number (from `cluster.json` `.epoch`) | | |
| TLS fingerprint (SHA-256 of `peer-tls.crt`) | | |
| OS version | | |
| IP address on test LAN | | |
| mDNS advertised port (visible after launch) | | |

TLS fingerprint command:

```bash
openssl x509 -in "$SA_TEST_ROOT/system-analyzer/peer-tls.crt" \
  -noout -fingerprint -sha256
```

---

## 7. Scenario Format

Each scenario uses the following table:

| Field | Content |
|---|---|
| **ID** | SC-NN |
| **Title** | Short name |
| **Preconditions** | Required state before the test step |
| **Action** | What the tester does |
| **Expected** | What should happen |
| **Observed** | *Fill in during test run* |
| **Evidence** | Log snippet, screenshot path, or UI state description (no secrets) |
| **Result** | PASS / FAIL / NOT VERIFIED |

---

## 8. Failure Classification Taxonomy

When a scenario does not PASS, classify the failure using one of:

| Code | Meaning |
|---|---|
| **PRODUCT BUG** | The app behaved incorrectly; code change needed |
| **TEST/ENVIRONMENT ISSUE** | Network/OS/test-setup problem, not an app defect |
| **DOCUMENTATION DRIFT** | Behavior is correct but docs/runbook is wrong |
| **NOT VERIFIED** | Test not executed (machine unavailable, scenario blocked) |

---

## 9. Scenarios

### SC-01 — NODE A Discovers NODE B via mDNS

| Field | Content |
|---|---|
| **ID** | SC-01 |
| **Preconditions** | Both nodes running isolated instances, same LAN subnet, neither has paired with the other |
| **Action** | Launch both nodes.  Wait up to 60 seconds.  On NODE A, open Nodes → Discovered Peers. |
| **Expected** | NODE B appears in the Discovered Peers list with a hostname, port, and identity fingerprint.  NODE B's status is "Discovered" (not paired). |
| **Observed** | |
| **Evidence** | Screenshot of Discovered Peers panel on NODE A.  NODE B's identity fingerprint (first 12 hex chars only). |
| **Result** | |

### SC-02 — NODE B Discovers NODE A via mDNS

| Field | Content |
|---|---|
| **ID** | SC-02 |
| **Preconditions** | SC-01 passed; both nodes running |
| **Action** | On NODE B, open Nodes → Discovered Peers. |
| **Expected** | NODE A appears in the Discovered Peers list. |
| **Observed** | |
| **Evidence** | Screenshot of Discovered Peers panel on NODE B. |
| **Result** | |

### SC-03 — Discovery Loss: NODE B Goes Offline

| Field | Content |
|---|---|
| **ID** | SC-03 |
| **Preconditions** | SC-01 passed; NODE B visible on NODE A |
| **Action** | Quit NODE B (clean shutdown).  Wait up to 90 seconds.  Observe NODE A's Discovered Peers panel. |
| **Expected** | NODE B disappears from NODE A's Discovered Peers list within the mDNS TTL window (up to ~60s). |
| **Observed** | |
| **Evidence** | Before/after screenshots; approximate elapsed time until removal. |
| **Result** | |

### SC-04 — Discovery Recovery: NODE B Comes Back

| Field | Content |
|---|---|
| **ID** | SC-04 |
| **Preconditions** | SC-03 passed; NODE B absent from NODE A's discovery list |
| **Action** | Relaunch NODE B with same isolated profile.  Wait up to 60 seconds.  Observe NODE A. |
| **Expected** | NODE B reappears in NODE A's Discovered Peers list.  Same identity fingerprint as in SC-01. |
| **Observed** | |
| **Evidence** | Screenshot; identity fingerprint comparison. |
| **Result** | |

### SC-05 — mDNS Service Type Visible on Network

| Field | Content |
|---|---|
| **ID** | SC-05 |
| **Preconditions** | NODE A running |
| **Action** | From any machine on the LAN, run: `avahi-browse _system-analyzer._tcp` or `dns-sd -B _system-analyzer._tcp` |
| **Expected** | NODE A's service appears with service type `_system-analyzer._tcp.local.`, hostname, and the OS-assigned port. |
| **Observed** | |
| **Evidence** | Terminal output (truncate after service name and port; no secrets present). |
| **Result** | |

---

> **Phase 12A Windows Defect Note (2026-09-17, pre-fix commit):**
> SC-06 through SC-55 were blocked on Windows by a failure at Boundary B
> (TLS credential generation). `ensure_tls_material` called
> `subprocess.run(["openssl", ...], check=True, stderr=DEVNULL)`. On Windows,
> `openssl.exe` is not on PATH, raising a silent `FileNotFoundError` before
> the TLS server could start. Fixed in Phase 12A by replacing subprocess with
> the `cryptography` Python library. Existing Linux/macOS certs are unaffected.
> Windows physical validation is pending real hardware. Update this table after
> the Windows run.
>
> | Scenario | Pre-fix (Windows) | Post-fix (Windows physical) |
> |---|---|---|
> | SC-06 Pairing | FAIL (Boundary B) | NOT VERIFIED — run needed |
> | SC-17 Join | FAIL (depends on SC-06) | NOT VERIFIED |
> | SC-43 Failover | NOT VERIFIED | NOT VERIFIED |

---

### SC-06 — Real Pairing: NODE A Initiates, NODE B Accepts

| Field | Content |
|---|---|
| **ID** | SC-06 |
| **Preconditions** | SC-01 passed; neither node has paired with the other |
| **Action** | On NODE A, select NODE B from Discovered Peers → Pair.  Follow the pairing dialog on NODE A.  On NODE B, accept the incoming pairing request in the pairing dialog. |
| **Expected** | Pairing completes.  NODE B appears in NODE A's Trusted Nodes list with status "Online".  NODE A appears in NODE B's Trusted Nodes list with status "Online".  TLS connection established (no certificate error). |
| **Observed** | |
| **Evidence** | Screenshots of Trusted Nodes panels on both machines showing each other with Online status. |
| **Result** | |

### SC-07 — Directionality Proof: Asymmetric Trust Before Mutual Pair

| Field | Content |
|---|---|
| **ID** | SC-07 |
| **Preconditions** | Fresh isolated profiles on both nodes (before any pairing) |
| **Action** | Pair NODE A → NODE B as in SC-06, but deliberately do NOT accept on NODE B (cancel the pairing dialog on NODE B).  Observe NODE A's Trusted Nodes and NODE B's Trusted Nodes. |
| **Expected** | NODE A does not add NODE B to its trusted list (pairing is bilateral; incomplete pairing produces no trust on either side).  Both nodes remain unpaired. |
| **Observed** | |
| **Evidence** | Screenshots showing Trusted Nodes empty on both machines. |
| **Result** | |

### SC-08 — Bilateral Pairing: Both Nodes Pair Each Other

| Field | Content |
|---|---|
| **ID** | SC-08 |
| **Preconditions** | SC-06 passed — NODE A and NODE B have mutually paired |
| **Action** | On NODE B, inspect the Trusted Nodes panel.  Confirm NODE A is present.  On NODE A, confirm NODE B is present. |
| **Expected** | Trust is bilateral: NODE A trusts NODE B AND NODE B trusts NODE A.  Both show "Online" connection status. |
| **Observed** | |
| **Evidence** | Screenshots of both Trusted Nodes panels. |
| **Result** | |

### SC-09 — Auth Failure: Wrong HMAC During Pairing Attempt

| Field | Content |
|---|---|
| **ID** | SC-09 |
| **Preconditions** | Isolated profiles; no prior pairing between the two nodes |
| **Action** | Attempt pairing between NODE A and NODE B using a deliberately wrong pairing code (type one digit incorrectly in the pairing dialog). |
| **Expected** | Pairing fails.  The UI shows an error message (authentication failure or code mismatch).  No trust records created on either node.  The connection status for the failed peer does NOT show "Online". |
| **Observed** | |
| **Evidence** | Screenshot of error dialog.  Confirm `cluster.json` on both nodes has no new trusted_nodes entry for the other. |
| **Result** | |

### SC-10 — Identity Mismatch Detection

| Field | Content |
|---|---|
| **ID** | SC-10 |
| **Preconditions** | SC-06 passed (nodes paired and Online); keep both running |
| **Action** | On NODE B, manually replace `peer-tls.crt` and `peer-tls.key` with freshly generated self-signed cert/key for a different identity.  Restart NODE B.  Wait up to 60s and observe NODE A's Trusted Nodes panel. |
| **Expected** | NODE A detects the TLS fingerprint mismatch.  NODE B's entry in NODE A's Trusted Nodes shows connection status "Identity changed" (or equivalent warning).  The row is NOT openable/selectable. |
| **Observed** | |
| **Evidence** | Screenshot of NODE A's Trusted Nodes panel showing the "Identity changed" status label. |
| **Result** | |

### SC-11 — Connection Status: ONLINE Visible in UI

| Field | Content |
|---|---|
| **ID** | SC-11 |
| **Preconditions** | SC-06 passed; both nodes running; both Online |
| **Action** | On NODE A, observe NODE B's entry in the Trusted Nodes panel.  Check the status label. |
| **Expected** | Status label reads "Online".  Status color is green (success role). |
| **Observed** | |
| **Evidence** | Screenshot showing status label. |
| **Result** | |

### SC-12 — Connection Status: OFFLINE + Retrying

| Field | Content |
|---|---|
| **ID** | SC-12 |
| **Preconditions** | SC-06 passed; both nodes Online |
| **Action** | On NODE B, block outbound traffic to NODE A's port (iptables drop or disconnect the cable).  Wait up to 30s.  Observe NODE A's Trusted Nodes panel. |
| **Expected** | NODE B's entry transitions to status "Offline · retrying".  `retry_automatic` is True (automatic retry visible in UI text). |
| **Observed** | |
| **Evidence** | Screenshot showing "Offline · retrying" label. |
| **Result** | |

### SC-13 — Reconnect After Network Restored

| Field | Content |
|---|---|
| **ID** | SC-13 |
| **Preconditions** | SC-12 executed; NODE B showing "Offline · retrying" on NODE A |
| **Action** | Restore network connectivity.  Wait up to 60s. |
| **Expected** | NODE B's status transitions back to "Online" without any user action. |
| **Observed** | |
| **Evidence** | Screenshot of NODE A's Trusted Nodes showing Online status after restoration.  Approximate time to recover. |
| **Result** | |

### SC-14 — Manual Disconnect: Remove Connection

| Field | Content |
|---|---|
| **ID** | SC-14 |
| **Preconditions** | SC-06 passed; both nodes Online |
| **Action** | On NODE A, open NODE B's entry in Trusted Nodes → Remove Connection.  Confirm the prompt. |
| **Expected** | NODE B's status on NODE A changes to "Disconnected" (not "Offline · retrying").  No automatic reconnect attempt.  Trust record preserved (NODE B still appears in list but as Disconnected).  `manual_disconnected=True` reflected in UI. |
| **Observed** | |
| **Evidence** | Screenshot showing "Disconnected" status label.  Confirm no retry spinning indicator. |
| **Result** | |

### SC-15 — Auth Failure Status Visible in UI

| Field | Content |
|---|---|
| **ID** | SC-15 |
| **Preconditions** | Isolated profiles; NODE A has a trust record for NODE B (paired), but NODE B's HMAC secret has been rotated (e.g., restore a backup of NODE A's `cluster.json` with a different secret than what NODE B currently knows) |
| **Action** | With mismatched HMAC secrets, restart both nodes.  Wait up to 60s.  Observe NODE A's Trusted Nodes panel. |
| **Expected** | NODE B's entry shows status "Auth failed".  `retry_automatic=False` (no automatic retry — this is an auth-class failure). |
| **Observed** | |
| **Evidence** | Screenshot showing "Auth failed" status label.  No retry spinner. |
| **Result** | |

### SC-16 — CONNECTING Status Visible During Startup

| Field | Content |
|---|---|
| **ID** | SC-16 |
| **Preconditions** | SC-06 passed; NODE B is offline |
| **Action** | Start NODE A first (while NODE B is still offline).  Immediately observe NODE B's entry in NODE A's Trusted Nodes panel. |
| **Expected** | NODE B's entry briefly shows "Connecting…" before transitioning to "Offline · retrying". |
| **Observed** | |
| **Evidence** | Screenshot taken within the first 10 seconds showing "Connecting…" label (best-effort; the transition may be fast). |
| **Result** | |

### SC-17 — Cluster Join: NODE B Joins NODE A's Cluster

| Field | Content |
|---|---|
| **ID** | SC-17 |
| **Preconditions** | SC-06 passed; both nodes mutually paired and Online; NODE A is Coordinator |
| **Action** | On NODE A, generate a cluster invite for NODE B (Cluster page → Invite → copy invite code).  On NODE B, consume the invite (Cluster page → Join → paste invite code). |
| **Expected** | NODE B joins NODE A's cluster as Worker.  NODE B's role in `cluster.json` is "worker".  NODE A's `cluster.json` shows NODE B as an enrolled member.  Both nodes display the same cluster ID. |
| **Observed** | |
| **Evidence** | Screenshots of Cluster pages on both machines.  Cluster ID match confirmed. |
| **Result** | |

### SC-18 — Restart After Join: Membership Persists

| Field | Content |
|---|---|
| **ID** | SC-18 |
| **Preconditions** | SC-17 passed; both nodes running |
| **Action** | Quit and relaunch both NODE A and NODE B (in either order). |
| **Expected** | NODE B retains its Worker role after restart.  Cluster membership survives restart on both nodes.  Both nodes reconnect and show Online status for each other. |
| **Observed** | |
| **Evidence** | Screenshots of Cluster pages after restart.  `cluster.json` contents (role and cluster_id fields only; no secrets). |
| **Result** | |

### SC-19 — Role Mutation: Promote NODE B to Subcoordinator

| Field | Content |
|---|---|
| **ID** | SC-19 |
| **Preconditions** | SC-17 passed; NODE B is Worker; NODE A is Coordinator and Online |
| **Action** | On NODE A (Coordinator), change NODE B's role to Subcoordinator via the Cluster page role control. |
| **Expected** | NODE B's role updates to Subcoordinator on both machines.  The role change is committed REMOTE FIRST (sent to NODE B) then confirmed locally on NODE A.  `cluster.json` on both nodes reflects "subcoordinator". |
| **Observed** | |
| **Evidence** | Screenshots of Cluster pages on both machines showing Subcoordinator role.  Approximate time for role to propagate. |
| **Result** | |

### SC-20 — Role Mutation: Demote NODE B Back to Worker

| Field | Content |
|---|---|
| **ID** | SC-20 |
| **Preconditions** | SC-19 passed; NODE B is Subcoordinator |
| **Action** | On NODE A, change NODE B's role back to Worker. |
| **Expected** | NODE B's role reverts to Worker on both machines.  `cluster.json` updated accordingly. |
| **Observed** | |
| **Evidence** | Screenshots of Cluster pages. |
| **Result** | |

### SC-21 — Role Lock: Only Coordinator Can Change Roles

| Field | Content |
|---|---|
| **ID** | SC-21 |
| **Preconditions** | SC-17 passed; NODE B is Worker; NODE B is Online |
| **Action** | On NODE B (Worker), attempt to change NODE A's role or its own role via the Cluster page. |
| **Expected** | The role control is disabled or returns an error.  NODE B cannot mutate roles — only the Coordinator has authority.  No role change is committed. |
| **Observed** | |
| **Evidence** | Screenshot of disabled/error state on NODE B's Cluster page. |
| **Result** | |

### SC-22 — Pause NODE B

| Field | Content |
|---|---|
| **ID** | SC-22 |
| **Preconditions** | SC-17 passed; NODE B is Worker and Online |
| **Action** | On NODE A, pause NODE B (Cluster page → NODE B → Pause). |
| **Expected** | NODE B's cluster status transitions to Paused on both machines.  NODE B cannot accept new work (no active job capability asserted). |
| **Observed** | |
| **Evidence** | Screenshots of Cluster pages showing Paused status. |
| **Result** | |

### SC-23 — Resume NODE B

| Field | Content |
|---|---|
| **ID** | SC-23 |
| **Preconditions** | SC-22 passed; NODE B is Paused |
| **Action** | On NODE A, resume NODE B. |
| **Expected** | NODE B transitions back to Worker (active) status.  Both Cluster pages updated. |
| **Observed** | |
| **Evidence** | Screenshots showing resumed status. |
| **Result** | |

### SC-24 — Paused Node Cannot Promote to Coordinator

| Field | Content |
|---|---|
| **ID** | SC-24 |
| **Preconditions** | SC-19 passed; NODE B is Subcoordinator; pause NODE B (SC-22) |
| **Action** | Wait for current Coordinator lease to expire (≥ 120 seconds from last renewal).  Observe whether NODE B promotes. |
| **Expected** | NODE B does NOT promote to Coordinator while paused.  `can_promote()` returns False when paused.  The paused status is respected even after lease expiry. |
| **Observed** | |
| **Evidence** | `cluster.json` on NODE B after 120+ seconds showing role remains "subcoordinator" and no promotion occurred. |
| **Result** | |

### SC-25 — Dashboard Sharing: NODE A Shares with NODE B

| Field | Content |
|---|---|
| **ID** | SC-25 |
| **Preconditions** | SC-06 passed; both nodes paired and Online; NODE A has Dashboard Read permission granted to NODE B |
| **Action** | On NODE A, enable dashboard sharing with NODE B (Sharing dialog → NODE B → Share Dashboard).  On NODE B, open NODE A's dashboard. |
| **Expected** | NODE B can view NODE A's dashboard data.  NODE A's sharing consent flag is True in the in-memory `_peer_dashboard_shares` dict. |
| **Observed** | |
| **Evidence** | Screenshots of NODE A's dashboard visible from NODE B. |
| **Result** | |

### SC-26 — Dashboard Share: Explicit Consent Required

| Field | Content |
|---|---|
| **ID** | SC-26 |
| **Preconditions** | SC-06 passed; both nodes Online; NODE A has NOT shared dashboard with NODE B |
| **Action** | On NODE B, attempt to view NODE A's dashboard without NODE A having granted sharing consent. |
| **Expected** | Access is denied.  NODE A's data is not visible to NODE B.  No error on NODE A beyond an access-denied log entry. |
| **Observed** | |
| **Evidence** | Screenshot of denied/empty state on NODE B when attempting to view NODE A. |
| **Result** | |

### SC-27 — Dashboard Share Revoke (Manual)

| Field | Content |
|---|---|
| **ID** | SC-27 |
| **Preconditions** | SC-25 passed; NODE B can view NODE A's dashboard |
| **Action** | On NODE A, revoke dashboard sharing with NODE B (Sharing dialog → NODE B → Stop Sharing). |
| **Expected** | NODE B can no longer view NODE A's dashboard.  Subsequent attempts return access denied.  NODE A's `_peer_dashboard_shares` entry for NODE B is removed. |
| **Observed** | |
| **Evidence** | Screenshot from NODE B attempting to view NODE A dashboard after revoke — access denied. |
| **Result** | |

### SC-28 — Dashboard Share Clears on Restart

| Field | Content |
|---|---|
| **ID** | SC-28 |
| **Preconditions** | SC-25 passed; NODE B can view NODE A's dashboard |
| **Action** | Restart NODE A (quit and relaunch with same isolated profile).  After NODE A fully starts and NODE B reconnects, attempt to view NODE A's dashboard from NODE B. |
| **Expected** | Dashboard share is NOT automatically restored after restart.  `_peer_dashboard_shares` is an in-memory dict cleared on startup.  NODE B receives access denied until NODE A explicitly re-enables sharing. |
| **Observed** | |
| **Evidence** | Screenshot of denied access immediately after restart; then screenshot after NODE A manually re-enables sharing to confirm the mechanism still works. |
| **Result** | |

### SC-29 — Dashboard Share is One-Directional

| Field | Content |
|---|---|
| **ID** | SC-29 |
| **Preconditions** | SC-25 passed; NODE A shares dashboard with NODE B (NODE B can read NODE A) |
| **Action** | On NODE A, attempt to view NODE B's dashboard without NODE B having granted sharing. |
| **Expected** | NODE A cannot read NODE B's dashboard.  Share is not symmetric; NODE A granting share to NODE B does not imply NODE B grants share to NODE A. |
| **Observed** | |
| **Evidence** | Screenshot of denied/empty state on NODE A when viewing NODE B. |
| **Result** | |

### SC-30 — Dashboard Share Requires Target-Owner Consent

| Field | Content |
|---|---|
| **ID** | SC-30 |
| **Preconditions** | SC-06 passed; both nodes Online |
| **Action** | Inspect the dashboard sharing UI on NODE A.  Confirm the sharing dialog shows only NODE A's own consent for outbound shares (not NODE B's data). |
| **Expected** | Dashboard sharing is local consent only.  NODE A controls who can read NODE A.  NODE B controls who can read NODE B.  There is no cross-node consent delegation. |
| **Observed** | |
| **Evidence** | Screenshot of sharing dialog showing only local controls. |
| **Result** | |

### SC-31 — Remove Connection (Trust Preserved)

| Field | Content |
|---|---|
| **ID** | SC-31 |
| **Preconditions** | SC-06 passed; both nodes Online |
| **Action** | On NODE A, Remove Connection for NODE B (confirm the prompt).  Inspect NODE A's `cluster.json`. |
| **Expected** | NODE B's status in NODE A's Trusted Nodes shows "Disconnected" (not "Offline").  No automatic retry initiated.  The trust record for NODE B still exists in `cluster.json` (Remove Connection != Revoke). |
| **Observed** | |
| **Evidence** | Screenshot of "Disconnected" status; excerpt of `cluster.json` trusted_nodes entry showing NODE B still present. |
| **Result** | |

### SC-32 — Re-pair After Remove Connection

| Field | Content |
|---|---|
| **ID** | SC-32 |
| **Preconditions** | SC-31 passed; NODE B shows "Disconnected" on NODE A |
| **Action** | On NODE A, initiate re-pairing with NODE B (discover via mDNS, pair again). |
| **Expected** | Pairing succeeds.  Connection re-established.  NODE B shows "Online" on NODE A after successful re-pair. |
| **Observed** | |
| **Evidence** | Screenshot showing Online status after re-pair. |
| **Result** | |

### SC-33 — Revoke: NODE A Revokes NODE B (NODE B Online)

| Field | Content |
|---|---|
| **ID** | SC-33 |
| **Preconditions** | SC-06 passed; both nodes mutually paired and Online |
| **Action** | On NODE A, revoke the trust record for NODE B (Trusted Nodes → NODE B → Revoke). |
| **Expected** | NODE A sends `revoke_self` wire op to NODE B.  Both nodes remove the trust record for the other from `cluster.json`.  Trust is revoked bilaterally.  NODE B no longer appears in NODE A's Trusted Nodes.  NODE A no longer appears in NODE B's Trusted Nodes. |
| **Observed** | |
| **Evidence** | Screenshots of Trusted Nodes on both machines showing empty/absent entries.  `cluster.json` excerpts showing removal (cluster_id and role lines only; no secrets). |
| **Result** | |

### SC-34 — Revoke While NODE B Offline (PendingTrustRevocation)

| Field | Content |
|---|---|
| **ID** | SC-34 |
| **Preconditions** | SC-06 passed; both nodes mutually paired; NODE B is offline |
| **Action** | On NODE A, revoke NODE B's trust record while NODE B is offline.  Note the result on NODE A.  Then bring NODE B back online. |
| **Expected** | NODE A queues the revocation as `PendingTrustRevocation` (durable outbox).  NODE A's Trusted Nodes shows NODE B as revoked/removed locally.  When NODE B comes back online, the queued `revoke_self` wire op is delivered.  NODE B removes NODE A from its trust records upon delivery. |
| **Observed** | |
| **Evidence** | Screenshot of NODE A immediately after revoke (NODE B absent).  Screenshot of NODE B's Trusted Nodes after it comes back online (NODE A absent).  Log line from NODE B showing revoke delivery (timestamp only; no secret content). |
| **Result** | |

### SC-35 — Revoke: NODE B Revokes NODE A

| Field | Content |
|---|---|
| **ID** | SC-35 |
| **Preconditions** | SC-06 passed; both nodes mutually paired and Online |
| **Action** | On NODE B, revoke NODE A's trust record. |
| **Expected** | Same bilateral behavior as SC-33 — both nodes remove the trust record for the other.  The initiating node is NODE B this time. |
| **Observed** | |
| **Evidence** | Screenshots of Trusted Nodes on both machines after revoke. |
| **Result** | |

### SC-36 — Re-pair After Revoke

| Field | Content |
|---|---|
| **ID** | SC-36 |
| **Preconditions** | SC-33 completed; trust revoked on both sides |
| **Action** | Rediscover NODE B via mDNS.  Pair again using the pairing dialog. |
| **Expected** | Re-pairing succeeds.  New trust record created on both nodes.  Connection status returns to Online.  No residue from the previous revoke session. |
| **Observed** | |
| **Evidence** | Screenshot of Online status after re-pair. |
| **Result** | |

### SC-37 — Re-join After Revoke (Cluster Membership Cleared)

| Field | Content |
|---|---|
| **ID** | SC-37 |
| **Preconditions** | SC-17 passed (NODE B was in cluster); then SC-33 executed (trust revoked) |
| **Action** | After re-pairing (SC-36), have NODE A generate a new invite.  Have NODE B consume the invite to rejoin. |
| **Expected** | NODE B rejoins the cluster as a fresh Worker with a new cluster membership.  Previous cluster history is separate from the new membership.  Role defaults to Worker. |
| **Observed** | |
| **Evidence** | Screenshots of Cluster pages after rejoin. |
| **Result** | |

### SC-38 — Coordinator Lease Propagates to Enrolled Members

| Field | Content |
|---|---|
| **ID** | SC-38 |
| **Preconditions** | SC-17 passed; NODE B is enrolled Worker; both nodes Online |
| **Action** | On NODE B, inspect the current epoch details (Cluster page or `cluster.json`).  Check `lease_expires_at`. |
| **Expected** | NODE B knows the current epoch's `lease_expires_at` value (received from NODE A via heartbeat).  The value matches what NODE A has in its own `cluster.json`. |
| **Observed** | |
| **Evidence** | `cluster.json` epoch excerpt from both nodes (epoch number and lease_expires_at only). |
| **Result** | |

### SC-39 — Lease Renewal Cycle (~Every 80 Seconds)

| Field | Content |
|---|---|
| **ID** | SC-39 |
| **Preconditions** | SC-38 passed; both nodes Online |
| **Action** | Record the initial `lease_expires_at` from NODE A's `cluster.json`.  Wait 80–100 seconds.  Re-read `lease_expires_at` from NODE A's `cluster.json`. |
| **Expected** | `lease_expires_at` has advanced by approximately 80–120 seconds (renewed within 40s of expiry, new lease = +120s from renewal time).  Lease duration remains 120 seconds. |
| **Observed** | |
| **Evidence** | Before and after `lease_expires_at` values from `cluster.json` (epoch lines only). |
| **Result** | |

### SC-40 — Lease Not Renewed When Coordinator Offline

| Field | Content |
|---|---|
| **ID** | SC-40 |
| **Preconditions** | SC-38 passed; both nodes Online; record current `lease_expires_at` |
| **Action** | Disconnect NODE A from the network (or block its outbound traffic).  Wait 30 seconds.  Check if `lease_expires_at` on NODE B has advanced. |
| **Expected** | With NODE A offline, no new heartbeats are sent.  `lease_expires_at` on NODE B does NOT advance.  The lease timestamp stays frozen until NODE A reconnects. |
| **Observed** | |
| **Evidence** | NODE B's `cluster.json` `lease_expires_at` unchanged after 30s of NODE A being offline. |
| **Result** | |

### SC-41 — Short Interruption (< 40s): No Failover Triggered

| Field | Content |
|---|---|
| **ID** | SC-41 |
| **Preconditions** | SC-19 passed; NODE B is Subcoordinator; both Online |
| **Action** | Disconnect NODE A for 20–35 seconds (less than 40s, well before lease renewal threshold).  Restore connectivity. |
| **Expected** | No failover.  NODE B does not promote.  NODE A reconnects and resumes as Coordinator.  Lease is renewed shortly after reconnect. |
| **Observed** | |
| **Evidence** | NODE B `cluster.json` role remains "subcoordinator" throughout.  NODE A `cluster.json` role remains "coordinator". |
| **Result** | |

### SC-42 — Medium Interruption (40–119s): Lease Renewal Missed, No Promotion Yet

| Field | Content |
|---|---|
| **ID** | SC-42 |
| **Preconditions** | SC-19 passed; NODE B is Subcoordinator; both Online |
| **Action** | Disconnect NODE A for 40–119 seconds (beyond the renewal window but before full lease expiry).  Restore connectivity. |
| **Expected** | NODE B's lease renewal is missed.  NODE B does not yet promote (lease not expired).  When NODE A reconnects, it renews the lease.  NODE A remains Coordinator throughout. |
| **Observed** | |
| **Evidence** | NODE B `cluster.json` role remains "subcoordinator".  Time of disconnection and reconnection recorded. |
| **Result** | |

### SC-43 — Real Failover (≥ 120s): Subcoordinator Promotes

| Field | Content |
|---|---|
| **ID** | SC-43 |
| **Preconditions** | SC-19 passed; NODE B is Subcoordinator; both Online; record current epoch number |
| **Action** | Disconnect NODE A completely (power off, or block all traffic).  Wait at least 130 seconds (full lease expiry = 120s + margin).  Observe NODE B. |
| **Expected** | After `lease_expires_at` passes (120s from last renewal), `can_promote()` becomes True on NODE B.  NODE B promotes itself to Coordinator.  NODE B's `cluster.json` role changes to "coordinator".  A new epoch is created with a new fencing token (token value not logged; only presence verified).  The epoch number increments. |
| **Observed** | |
| **Evidence** | NODE B `cluster.json` showing role="coordinator", new epoch number, fencing_token present (boolean: yes/no, not the value).  Approximate time from NODE A disconnect to promotion. |
| **Result** | |

### SC-44 — Old Coordinator Returns After Failover: Demoted to Worker

| Field | Content |
|---|---|
| **ID** | SC-44 |
| **Preconditions** | SC-43 passed; NODE B is now Coordinator; NODE A is offline |
| **Action** | Bring NODE A back online (restore connectivity or restart). |
| **Expected** | NODE A reconnects.  NODE A's stale epoch is rejected by NODE B (NODE B has a newer epoch).  NODE A is demoted to Worker via `_rejoin_stale_coordinator()`.  NODE A's `cluster.json` role changes to "worker".  NODE B remains Coordinator. |
| **Observed** | |
| **Evidence** | NODE A `cluster.json` role="worker" after reconnect.  NODE B `cluster.json` role="coordinator".  Log entry on NODE A showing stale epoch rejection (no secret values). |
| **Result** | |

### SC-45 — Stale Fence Token Rejected on Heartbeat

| Field | Content |
|---|---|
| **ID** | SC-45 |
| **Preconditions** | SC-43 passed; NODE B is Coordinator with new epoch; NODE A is Worker |
| **Action** | Observe the logs when NODE A sends its first heartbeat after rejoining (NODE A may still hold its old fencing token for a moment before demoting). |
| **Expected** | NODE B rejects any heartbeat that carries the OLD fencing token with a `FencingError`.  The stale heartbeat is silently dropped or triggers NODE A demotion.  The fence token value itself is NOT logged by either node. |
| **Observed** | |
| **Evidence** | Log entry showing fencing error or epoch rejection (no token value in log; confirm by grep). |
| **Result** | |

### SC-46 — Stale Coordinator: Two Independent Promotions Prevented

| Field | Content |
|---|---|
| **ID** | SC-46 |
| **Preconditions** | SC-19 passed; NODE B is Subcoordinator; requires a third scenario (informational — validate via code review if physical three-node setup unavailable) |
| **Action** | This scenario verifies that `promotion_epochs` prevents a Subcoordinator from promoting twice into the same epoch.  Verify in `cluster_roles.py` that `epoch.epoch not in state.promotion_epochs` is the gate. |
| **Expected** | Each epoch can only be promoted into once per Subcoordinator.  Duplicate promotion is blocked. |
| **Observed** | |
| **Evidence** | Code reference: `maintenance/components/cluster_roles.py` `can_promote()` check of `promotion_epochs`. |
| **Result** | |

### SC-47 — VPN/Firewall Blocks mDNS: Discovery Fails Gracefully

| Field | Content |
|---|---|
| **ID** | SC-47 |
| **Preconditions** | Both nodes running; NODE A and NODE B on separate VLANs or with mDNS blocked between them |
| **Action** | Run both nodes on a network segment where mDNS is filtered (e.g., different VLANs without mDNS proxy).  Observe NODE A's Discovered Peers panel. |
| **Expected** | NODE B does NOT appear in NODE A's Discovered Peers.  No crash.  The UI shows an empty discovered list.  No error dialog. |
| **Observed** | |
| **Evidence** | Screenshot of empty Discovered Peers panel.  Network topology description. |
| **Result** | |

### SC-48 — Direct IP Connection When mDNS Unavailable

| Field | Content |
|---|---|
| **ID** | SC-48 |
| **Preconditions** | SC-47 conditions; mDNS blocked but direct TCP reachable between nodes |
| **Action** | If the nodes have previously paired, confirm that the stored host/port in `cluster.json` can still be used for direct connection even without mDNS rediscovery. |
| **Expected** | Trusted nodes with stored host/port reconnect directly without requiring mDNS rediscovery.  The connection is attempted from the persisted endpoint in `cluster.json`. |
| **Observed** | |
| **Evidence** | Log showing direct TCP connection to stored endpoint (no mDNS path used). |
| **Result** | |

### SC-49 — Listener Binds 0.0.0.0: Reachable from Any Interface

| Field | Content |
|---|---|
| **ID** | SC-49 |
| **Preconditions** | NODE A running |
| **Action** | On NODE A, verify the listening port: `ss -tlnp | grep python` or check app logs for bound port. |
| **Expected** | NODE A's `RemoteSocketServer` binds `0.0.0.0` with an OS-assigned ephemeral port.  The port is reachable from NODE B's IP.  The bound port matches what mDNS advertises. |
| **Observed** | |
| **Evidence** | Terminal output from `ss -tlnp` showing `0.0.0.0:<port>`.  mDNS-advertised port from SC-05 matches. |
| **Result** | |

### SC-50 — UI Consistency: All State Changes Reflected in Real Time

| Field | Content |
|---|---|
| **ID** | SC-50 |
| **Preconditions** | SC-06 passed; both nodes Online |
| **Action** | Perform a sequence of actions (disconnect, reconnect, role change, pause) and observe both UIs after each change.  Do not force-refresh the UI manually. |
| **Expected** | NODE A's UI reflects NODE B's state changes without manual refresh.  Status labels, role labels, and pausing indicators all update automatically as state changes propagate. |
| **Observed** | |
| **Evidence** | Note any state changes that required a manual refresh. |
| **Result** | |

### SC-51 — MOVABLE Dormant: No Workload Scheduling UI

| Field | Content |
|---|---|
| **ID** | SC-51 |
| **Preconditions** | Both nodes running (any state) |
| **Action** | Inspect the Cluster page and all node-action dialogs on both nodes. |
| **Expected** | No workload scheduling, task assignment, or MOVABLE controls are visible in the UI.  MOVABLE is dormant — the feature is present in the data model but has no production workload and no user-facing controls. |
| **Observed** | |
| **Evidence** | Screenshot confirming absence of MOVABLE/workload controls. |
| **Result** | |

### SC-52 — Performance: UI Responds Within 2 Seconds

| Field | Content |
|---|---|
| **ID** | SC-52 |
| **Preconditions** | Both nodes running; cluster joined (SC-17 passed) |
| **Action** | Perform common actions (switch pages, open node details, open sharing dialog) and measure subjective response time. |
| **Expected** | All UI interactions respond within 2 seconds.  No janky freezing or unresponsive dialogs.  Background networking (heartbeat, lease renewal) does not block the UI thread. |
| **Observed** | |
| **Evidence** | Qualitative notes on responsiveness.  Any UI freeze durations. |
| **Result** | |

### SC-53 — Clean Shutdown: NODE A

| Field | Content |
|---|---|
| **ID** | SC-53 |
| **Preconditions** | SC-17 passed; both nodes running; cluster active |
| **Action** | Quit NODE A via the normal window close button.  Observe NODE B immediately after NODE A quits. |
| **Expected** | NODE A shuts down cleanly without crash.  NODE B detects the disconnection and transitions NODE A's status to "Offline · retrying".  No error dialogs on NODE B. |
| **Observed** | |
| **Evidence** | Screenshot of NODE B showing NODE A as "Offline · retrying" after clean shutdown. |
| **Result** | |

### SC-54 — Clean Shutdown: NODE B

| Field | Content |
|---|---|
| **ID** | SC-54 |
| **Preconditions** | SC-17 passed; both nodes running; cluster active |
| **Action** | Quit NODE B via the normal window close button.  Observe NODE A after NODE B quits. |
| **Expected** | Same as SC-53 in reverse.  NODE A shows NODE B as "Offline · retrying" after NODE B shuts down cleanly. |
| **Observed** | |
| **Evidence** | Screenshot of NODE A showing NODE B as "Offline · retrying". |
| **Result** | |

### SC-55 — Persistence Review: State Files After Full Run

| Field | Content |
|---|---|
| **ID** | SC-55 |
| **Preconditions** | After completing SC-01 through SC-54 |
| **Action** | Inspect the state files in `$SA_TEST_ROOT/system-analyzer/` on both nodes.  Check: `cluster.json` structure, SQLite DB tables, TLS cert validity. |
| **Expected** | `cluster.json` contains expected fields (node_id, cluster_id, role, trusted_nodes, epoch).  `cluster-history.sqlite3` exists and is non-empty.  TLS cert on both nodes is valid self-signed cert (not expired).  No plaintext secrets in `cluster.json` fields visible to tester (HMAC secret should be stored but not echoed in logs). |
| **Observed** | |
| **Evidence** | `cluster.json` file listing (node_id, cluster_id, role, epoch fields only — NO HMAC or key material).  SQLite table counts: `sqlite3 cluster-history.sqlite3 "SELECT count(*) FROM events;"`. |
| **Result** | |

---

## 10. Post-Run Checklist

Complete this after all scenarios are attempted.

- [ ] All PASS/FAIL/NOT VERIFIED rows filled in
- [ ] All FAIL rows classified using the taxonomy in §8
- [ ] No raw fencing token values appear in any Evidence field
- [ ] No HMAC secret values appear in any Evidence field  
- [ ] No TLS private key material in any Evidence field
- [ ] Screenshots/logs with accidental secret exposure are redacted before storage
- [ ] `cluster.json` excerpts contain only structural fields (no credential fields)
- [ ] Log review checklist (§11) completed
- [ ] Persistence review checklist (§12) completed
- [ ] Any PRODUCT BUG items have a filed issue or inline note in §9

---

## 11. Log Review Checklist

Run against the logs produced during the test run (redirect stdout/stderr to a file
before launching the app: `XDG_CONFIG_HOME=... python main.py > sa-node-a.log 2>&1`).

```bash
# Run on BOTH node log files. NONE of these should match.
grep -iE "hmac|secret|private.?key|fenc(e|ing).?token" sa-node-a.log
grep -iE "hmac|secret|private.?key|fenc(e|ing).?token" sa-node-b.log
```

- [ ] No HMAC secrets in logs
- [ ] No private key material in logs
- [ ] No raw fencing token values in logs (fencing error messages that say "stale" or "rejected" are acceptable, as long as they do not include the token value)
- [ ] No stack traces with embedded credential data
- [ ] `FencingError` entries (if any) do not include the token value
- [ ] `revoke_self` delivery log entries (if any) include peer ID but not secret material
- [ ] Connection auth failure log entries include peer ID and error type but not HMAC material

---

## 12. Persistence Review Checklist

Run on the state files in `$SA_TEST_ROOT/system-analyzer/`.

```bash
# Check cluster.json structure (safe fields only):
python3 -c "
import json, sys
d = json.load(open('$SA_TEST_ROOT/system-analyzer/cluster.json'))
safe = {k: d[k] for k in ('node_id','cluster_id','role','epoch') if k in d}
print(json.dumps(safe, indent=2))
"
```

- [ ] `cluster.json` is valid JSON and readable
- [ ] `node_id` is a non-empty string
- [ ] `cluster_id` is a non-empty string
- [ ] `role` is one of: `coordinator`, `worker`, `subcoordinator`
- [ ] `trusted_nodes` array present; entries have `node_id`, `hostname`, `host`, `port`
- [ ] `peer-tls.crt` is a valid X.509 certificate: `openssl x509 -in peer-tls.crt -noout -text | head -5`
- [ ] `peer-tls.crt` is not expired
- [ ] `cluster-history.sqlite3` exists and contains at least one row after SC-17
- [ ] `cluster-standby.sqlite3` exists after SC-17

---

## 13. Automated Regression Gate

Before any code change identified during physical testing, run the full automated test
suite to confirm baseline.  After any fix, run it again.

```bash
cd /path/to/system-analyzer
python3 -m pytest tests/ -x -q
```

Expected: **all tests pass** on a clean checkout at v1.6.0.4.

The automated suite does NOT substitute for this runbook.  Passing automated tests
establishes that individual units behave correctly.  This runbook establishes that the
full integrated system works across two real machines on a real network.

---

*End of runbook.  Fill in Observed, Evidence, and Result columns during a physical
two-machine test session.*
