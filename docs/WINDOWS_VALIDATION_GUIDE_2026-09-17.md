# Windows Physical Validation Guide — Phase 12B / 12C

**Date:** 2026-09-17  
**Version:** 1.6.0.6  
**Status:** NOT STARTED — requires physical Windows hardware

> This guide translates Phase 12B/12C requirements into exact commands and
> record fields for the person holding the Windows machine.  Fill in every
> Observed/Result field.  Do not mark a scenario PASS based on unit test
> evidence.

---

## IMPORTANT: Windows test machine does NOT require the source repository

**The Windows machine is a black-box runtime node, not a development workstation.**

The workflow is:

```
LINUX  →  build wheel  →  WINDOWS: install wheel  →  run app  →  report results
LINUX  →  investigate + fix  →  build new wheel  →  WINDOWS: install updated wheel
```

**Do NOT install on Windows:**
- Git
- The source repository
- pytest, ruff, pyright, mypy, or any development tools
- IDE or compiler

**The only artifact Windows needs is the built wheel file.**

---

## Wheel Install (Phase 12C — do this first)

Obtain the wheel from the Linux build machine:

```
system_analyzer-1.6.0.6-py3-none-any.whl
SHA-256: 1cd944a67d0f6e3b60a41f2853f1043a16d1fd93bf8e829a55e5561797e70c72
```

On Windows PowerShell:

```powershell
# Verify SHA-256 matches the above before installing
Get-FileHash system_analyzer-1.6.0.6-py3-none-any.whl -Algorithm SHA256

# Install
pip install system_analyzer-1.6.0.6-py3-none-any.whl

# Verify cryptography was installed (required for TLS generation)
python -c "import cryptography; print('cryptography', cryptography.__version__)"

# Verify the installed package version
python -c "from maintenance._version import __version__; print(__version__)"
```

Expected output of last command: `1.6.0.6`

**If pip tries to compile a C extension:** that is a packaging defect — report it
to the Linux side before continuing.  Do not install a compiler.

---

## Prerequisites

- One physical Windows machine (NODE W) on the same LAN as the Linux NODE A
- Python 3.10+ installed on NODE W (from python.org or Microsoft Store)
- Both machines on the same subnet (mDNS multicast must reach both)
- The wheel file transferred to NODE W (USB, share, or download)

---

## 0. Environment Record (fill in before anything else)

| Field | Value |
|---|---|
| Windows edition | e.g. Windows 11 Home 23H2 |
| Build number | `winver` → e.g. 22631.3447 |
| Architecture | x64 / ARM64 |
| Python version | `python --version` |
| System Analyzer version | from `maintenance/_version.py` → 1.6.0.5 |
| Active network adapter | `Get-NetAdapter \| Where Status -eq 'Up'` |
| LAN IPv4 address | `Get-NetIPAddress -AddressFamily IPv4` |
| VPN running? | yes / no |
| Windows network profile | `Get-NetConnectionProfile` → Private / Public / Domain |
| Windows Defender Firewall | `Get-NetFirewallProfile \| Select Name,Enabled` |

---

## 1. openssl Test (Phase 12A proof)

Run in PowerShell or cmd:

```powershell
where.exe openssl
```

**Expected:** not found (or path like `C:\Program Files\Git\usr\bin\openssl.exe`).  
**Record result:**

| Test | Result |
|---|---|
| `where.exe openssl` output | |
| openssl version (if found) | |

---

## 2. Isolated Profile Setup

```powershell
$env:SA_TEST_ROOT = "$env:USERPROFILE\sa-physical-test-$(Get-Date -Format yyyyMMdd)"
New-Item -ItemType Directory -Path $env:SA_TEST_ROOT -Force
```

Launch with isolated APPDATA:

```powershell
$env:APPDATA = $env:SA_TEST_ROOT
cd C:\path\to\system-analyzer
python main.py 2>&1 | Tee-Object -FilePath "$env:SA_TEST_ROOT\sa-node-w.log"
```

---

## 3. TLS Material Generation (SC-05 Windows equivalent)

After first launch (app should start without openssl):

```powershell
# Verify files created in isolated profile
Get-ChildItem "$env:SA_TEST_ROOT\system-analyzer\"
```

**Expected files:** `cluster.json`, `preferences.json`, `peer-tls.crt`, `peer-tls.key`

**TLS fingerprint:**

```powershell
# PowerShell — compute SHA-256 of the cert DER bytes
$cert = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new("$env:SA_TEST_ROOT\system-analyzer\peer-tls.crt")
$bytes = $cert.RawData
$sha256 = [System.Security.Cryptography.SHA256]::Create().ComputeHash($bytes)
($sha256 | ForEach-Object { $_.ToString("x2") }) -join ''
```

Record first 12 hex chars only (enough to verify stability):

| Step | Fingerprint prefix (first 12 chars) | Files present? |
|---|---|---|
| First launch | | |
| After restart (§6) | | |

---

## 4. Listener Verification

After launch, check the TCP listener:

```powershell
Get-NetTCPConnection -State Listen | Where-Object { $_.OwningProcess -in (Get-Process python).Id }
```

Or with netstat:

```powershell
netstat -ano | findstr LISTENING | findstr -v "0.0.0.0:0"
```

**Expected:** `0.0.0.0:<ephemeral-port>` owned by `python.exe`

| Field | Observed |
|---|---|
| Bind address | |
| Port | |
| Process name | |

---

## 5. Windows Firewall Prompt

Launch the app and watch for the Windows Firewall prompt.

| Question | Answer |
|---|---|
| Prompt appeared? | yes / no |
| Private networks selected? | yes / no |
| Public networks selected? | yes / no |
| Source Python vs packaged EXE different? | (fill after packaged test) |

If no prompt appeared:

```powershell
# Check existing firewall rules for python
Get-NetFirewallRule -DisplayName "*python*" | Select DisplayName, Enabled, Direction, Action
```

---

## 6. Certificate Stability After Restart

Record fingerprint from step 3.  
Close app. Restart app.

```powershell
# Same fingerprint command as step 3
```

**Expected:** same fingerprint prefix.

Record in step 3 table.

---

## 7. mDNS Discovery (SC-01 / SC-02 from Windows side)

On the Linux NODE A, check discovered peers panel for NODE W.  
On NODE W, check Nodes & Connections → Discovered Peers for NODE A.

Optionally verify mDNS from PowerShell (requires DNS-SD or avahi-browse):

```powershell
# If DNS-SD client available:
dns-sd -B _system-analyzer._tcp
```

| Direction | NODE visible? | Fingerprint shown? |
|---|---|---|
| NODE A discovers NODE W | | |
| NODE W discovers NODE A | | |

---

## 8. If Discovery Fails

Classify by checking each layer independently:

**A. Listener reachable by known IP?**

From NODE A:

```bash
nc -z <NODEW-IP> <PORT> && echo "reachable" || echo "blocked"
```

**B. UDP multicast blocked?**

```powershell
# Check if UDP 5353 is passing through Windows Firewall
Get-NetFirewallRule | Where-Object { $_.Protocol -eq "UDP" -and $_.LocalPort -eq "5353" }
```

**C. Zeroconf service registered?**

Look for log line on NODE W: `Network discovery active for <node-id>`

**D. VPN/virtual adapter interference?**

```powershell
Get-NetAdapter | Select Name, InterfaceDescription, Status, MacAddress
Get-NetIPAddress -AddressFamily IPv4 | Select InterfaceAlias, IPAddress
```

Identify which addresses NODE W advertises and whether any are WSL/Hyper-V ranges.

| Check | Result |
|---|---|
| Listener TCP reachable from NODE A | |
| mDNS log line found | |
| Firewall UDP 5353 rule | |
| Adapters with active IPs (list) | |
| Addresses advertised via mDNS (from NODE A discovery) | |

---

## 9. Physical Pair: Linux NODE A → Windows NODE W

On NODE A, discover NODE W and click Pair.

**On NODE W:** watch for the pairing approval dialog.

Verify each step:

| Step | Result |
|---|---|
| NODE A sees fingerprint confirmation dialog | PASS/FAIL |
| NODE W approval dialog appears | PASS/FAIL |
| NODE A initiator UI remains responsive | PASS/FAIL |
| Pairing completes (no error) | PASS/FAIL |
| NODE A shows NODE W in Trusted Nodes (Online) | PASS/FAIL |
| NODE W shows NODE A in peer grants (`cluster.json`) | PASS/FAIL |
| Authenticated hello succeeds (Online status) | PASS/FAIL |

**Confirm directionality:**

```powershell
# NODE W cluster.json — should have peer_grants entry for NODE A
Get-Content "$env:SA_TEST_ROOT\system-analyzer\cluster.json" | python -c "
import json, sys
d = json.load(sys.stdin)
print('peer_grants:', len(d.get('peer_grants', [])))
print('trusted_nodes:', len(d.get('trusted_nodes', [])))
"
```

Expected: `peer_grants: 1`, `trusted_nodes: 0` (NODE W is target, not initiator).

---

## 10. Directionality Proof

After only Linux→Windows pair above:

On NODE W, attempt to open or read NODE A's data (without separate NODE W→NODE A pair).

**Expected:** operation denied or not available. No automatic bilateral trust.

| Check | Result |
|---|---|
| NODE W can read NODE A without separate pair | FAIL (expected) |
| Trust remains directional | PASS/FAIL |

---

## 11. Reverse Pair: Windows NODE W → Linux NODE A

Perform an explicit, separate pairing ceremony from NODE W as initiator.

| Step | Result |
|---|---|
| NODE W discovers NODE A | PASS/FAIL |
| NODE W click Pair | PASS/FAIL |
| NODE A approval dialog appears | PASS/FAIL |
| Reverse pair completes | PASS/FAIL |
| NODE W shows NODE A in Trusted Nodes (Online) | PASS/FAIL |
| NODE A shows NODE W in peer_grants | PASS/FAIL |

After this step, trust is bilateral and independent.

---

## 12. Restart NODE W — Identity Persistence

Close System Analyzer on NODE W. Restart.

```powershell
# Verify same node_id and fingerprint
Get-Content "$env:SA_TEST_ROOT\system-analyzer\cluster.json" | python -c "
import json, sys
d = json.load(sys.stdin)
print('node_id:', d.get('local_node_id', d.get('node_id','?')))
"
```

| Check | Result |
|---|---|
| Same NodeId after restart | PASS/FAIL |
| Same TLS fingerprint (from step 6) | PASS/FAIL |
| Peer grants preserved | PASS/FAIL |
| Trusted nodes preserved | PASS/FAIL |
| NODE A reconnects automatically | PASS/FAIL |
| No re-pair required | PASS/FAIL |

---

## 13. Connection States (Phase 11 on Windows)

| Status | Method | Observed label | Expected label |
|---|---|---|---|
| Online | both nodes running | | Online |
| Connecting | restart NODE W, immediately check NODE A | | Connecting… |
| Offline · retrying | block NODE W network; check NODE A | | Offline · retrying |
| Disconnected | Remove Connection on NODE A | | Disconnected |

---

## 14. Remove Connection

On NODE A, open NODE W entry → Remove Connection → confirm.

| Check | Result |
|---|---|
| Status shows "Disconnected" (not "Offline") | PASS/FAIL |
| No automatic retry | PASS/FAIL |
| Trust record preserved in NODE A cluster.json | PASS/FAIL |
| Reconnect after Remove Connection (no re-pair) | PASS/FAIL |

---

## 15. Revoke

On NODE A, revoke NODE W's trust record.

| Check | Result |
|---|---|
| NODE W disappears from NODE A Trusted Nodes | PASS/FAIL |
| NODE A disappears from NODE W peer_grants (if online) | PASS/FAIL |
| Re-discovery still possible | PASS/FAIL |
| Fresh pair creates new credentials | PASS/FAIL |
| Old credential fails after revoke | PASS/FAIL |

---

## 16. Join Cluster

With good pair state, run the cluster join flow.

Coordinator (NODE A) creates invite → NODE W consumes it.

| Check | Result |
|---|---|
| NODE W adopts cluster_id | PASS/FAIL |
| NODE W role = worker in cluster.json | PASS/FAIL |
| NODE A shows NODE W as enrolled member | PASS/FAIL |
| Cluster page updates on both machines | PASS/FAIL |
| Role persists after NODE W restart | PASS/FAIL |

---

## 17. Role RPC on Windows Worker

From NODE A (Coordinator), change NODE W's role.

| Check | Result |
|---|---|
| NODE W role → Subcoordinator | PASS/FAIL |
| NODE W role → Worker (revert) | PASS/FAIL |
| Pause NODE W | PASS/FAIL |
| Resume NODE W | PASS/FAIL |

---

## 18. Log Review

After all tests, review the log file:

```powershell
# No secrets should appear
Select-String -Path "$env:SA_TEST_ROOT\sa-node-w.log" -Pattern "hmac|secret|private.?key|fencing.?token" -CaseSensitive:$false
```

**Expected:** no matches.

```powershell
# No unhandled WinError
Select-String -Path "$env:SA_TEST_ROOT\sa-node-w.log" -Pattern "WinError|Traceback|CRITICAL|FileNotFoundError"
```

| Check | Result |
|---|---|
| HMAC/secret in logs | none (expected) |
| Private key in logs | none (expected) |
| Fencing token value in logs | none (expected) |
| Unhandled WinError | none (expected) |
| Traceback/CRITICAL | none (expected) |

---

## 19. Packaged Build (if applicable)

If a packaged Windows executable is distributed:

| Check | Result |
|---|---|
| Clean first launch generates TLS cert | PASS/FAIL |
| openssl.exe not required | PASS/FAIL |
| cryptography bundled in package | PASS/FAIL |
| Listener starts | PASS/FAIL |
| Discovery works | PASS/FAIL |
| Pair works | PASS/FAIL |
| Restart reconnects | PASS/FAIL |

---

## 20. Update Physical Runbook

After completing the above, update the main runbook at:

`docs/PHYSICAL_TWO_NODE_ACCEPTANCE_2026-09-17.md`

For each relevant scenario (SC-06, SC-08, SC-11 through SC-18, SC-31 through SC-37, SC-38 through SC-43, SC-53, SC-54, SC-55):

Fill in:
- **Observed**
- **Evidence** (redacted screenshots or log excerpts — no secrets)
- **Result**: PASS / FAIL / NOT VERIFIED

For each FAIL:
- Classification: PRODUCT BUG / TEST/ENVIRONMENT ISSUE / DOCUMENTATION DRIFT
- File an issue or note the fix commit

---

## WinError Reference

If Windows socket errors appear:

| WinError | Meaning | Expected UI state |
|---|---|---|
| 10013 | Permission denied (firewall) | Offline · retrying |
| 10054 | Connection reset by peer | Offline · retrying |
| 10060 | Connection timed out | Offline · retrying |
| 10061 | Connection refused (port closed) | Offline · retrying |

None of these should surface as "Authentication failed" — that status requires
an authenticated protocol exchange that actually rejected credentials.

---

## NOT VERIFIED After Phase 12B (if environment limited)

Mark these honestly if not physically tested:

- [ ] Reboot Windows (§20 of spec)
- [ ] VPN comparison (§34)
- [ ] Windows as Coordinator (§28)
- [ ] Windows as Subcoordinator (§29)
- [ ] Packaged build (§30) if no packaged build exists
- [ ] Windows↔Windows pair if only one Windows machine available

---

*Fill in all Observed/Result fields during the physical test session. Do not*
*mark NOT VERIFIED items as PASS from code audit alone.*
