# Windows Runtime Findings — system-analyzer 1.6.0.5

Machine: DESKTOP-0C2C5H3 (Windows 11 Home 10.0.26200), AMD Radeon GPU (no NVIDIA).
Installed via `irm https://raw.githubusercontent.com/20204166/exp/main/install/install-online.ps1 | iex`
(wheel: `system_analyzer-1.6.0.5-py3-none-any.whl`, upgraded from 1.6.0.3 already on the machine).
Log file: `C:\Users\BTN17\AppData\Local\system-analyzer\system-analyzer.log`
State dir: `C:\Users\BTN17\AppData\Roaming\system-analyzer\` (`cluster.json`, `cluster-history.sqlite3`, `peer-tls.{crt,key}`)

All findings below are reproduced on this physical Windows machine using the installed
wheel only — no source was cloned or edited.

---

## 1. CLI flags are completely ignored — `--help`/`--version`/any flag launches the GUI and hangs

**Repro:**
```powershell
system-analyzer --help
system-analyzer --version
system-analyzer --totally-bogus-flag-xyz
```
All three produce **identical** behavior: no stdout/stderr, no exit — the full GUI
("System Analyzer" window) launches and the process never returns. Confirmed via
process argv:
```
PID 15304 system-analyzer.exe --help  (parent)
PID 15036 python.exe "...\system-analyzer.exe" --help  (child, owns the GUI window)
```
Each hung until force-killed (`Stop-Process`). No CLI parsing / usage text / exit path
exists at all — the entry point ignores `sys.argv` entirely.

**Impact:** any scripted install-verification, CI smoke test, or `--version` check
against this wheel hangs forever instead of failing fast or succeeding fast.

---

## 2. No single-instance guard — two processes share the same node identity and state files

**Repro:** launch `system-analyzer` twice (no args) without closing the first.

Both instances log the **same** node id from the shared `cluster.json`:
```
2026-09-17 12:08:05 INFO maintenance.components.network_discovery: Network discovery active for node-b31a0913e76db7c60cb7c6ec82313660
```
(identical id to the first instance's earlier log lines). `cluster.json` shows this
node already self-assigned `"roles": ["coordinator", "worker"]` with an active
`coordinator_epoch`/`fencing_token`. Two live processes now both believe they are the
same coordinator node, both with write access to the same
`cluster-history.sqlite3` and `cluster.json`, with no lock file or mutex observed
anywhere in `%APPDATA%\system-analyzer` or `%LOCALAPPDATA%\system-analyzer`.

**Impact:** concurrent-write / split-brain coordinator risk any time a user
double-launches the app (e.g. via Start Menu + a leftover tray/background instance),
which is easy to do given finding #1 also silently spawns extra full instances.

---

## 3. Remote peer listener does not actually listen — failure went from *logged* to *silent* across versions

On 1.6.0.3 (this machine's history, 2026-09-13 → 09-16), every launch logged:
```
WARNING maintenance.ui.window_discovery: Remote peer listener unavailable: [WinError 2] The system cannot find the file specified
```
`WinError 2` = file-not-found, which is not a normal TCP-bind failure — consistent
with a POSIX-only code path (e.g. an `AF_UNIX` socket path or a helper executable
looked up by file path) being hit on Windows.

After upgrading to 1.6.0.5 today (12:03 onward), **this warning no longer appears at
all**, in either instance's log. But actual listening sockets, checked directly:
```
Get-NetTCPConnection -State Listen | Where OwningProcess -in 14212,8772
  0.0.0.0  56791  (PID 14212)
  0.0.0.0  52788  (PID 8772)
```
— both processes are listening on random ephemeral ports, **not** port 43737, which
is the port the UI displays under "Discovered peers → This System". So the
underlying listener-setup problem is still present; 1.6.0.5 just stopped logging it,
which is a diagnosability regression even if unrelated to the original bug.

---

## 4. Pairing fails with an unhelpful, completely unlogged error

User-driven repro: Settings → Local-network discovery → Pair on a discovered peer
labeled "This System" (port 43737, Node ID `node-f...73f51b` — **not** the same as
this machine's own `local_node_id` `node-b31a0913e76db7c60cb7c6ec82313660` in
`cluster.json`).

Result: dialog shows **"Target did not provision the peer grant"** and the pair
fails. `system-analyzer.log` gained **zero new lines** for this event — confirmed by
diffing the log file before/after the pairing attempt. No trace of the failure
exists outside the UI.

Root cause is most likely #1: earlier `--help`/`--version`/bogus-flag test runs each
spawned a full GUI+node instance that briefly advertised itself over mDNS before being
killed; this instance's stale/half-dead advertisement is what got discovered and
mislabeled "This System" (see #5), and pairing against it fails because the
advertising process no longer exists to complete grant provisioning.

---

## 5. Discovered peer mislabeled "This System" despite a different Node ID

The peer in #4 is shown under the heading **"This System"** in the Discovered peers
list, but its Node ID does not match this machine's actual `local_node_id`. The
real Windows hostname is `DESKTOP-0C2C5H3`, not "This System" — so the label isn't
derived from the hostname either. This looks like a same-machine/loopback heuristic
that doesn't actually verify identity, so a user could be misled into pairing with an
untrusted or stale peer while believing it's their own instance.

---

## 6. mDNS (UDP 5353) bound inconsistently across network interfaces between the two instances

```
PID 14212: fe80::fa4a:c059:d9e:c411%14 : 5353                         (1 interface)
PID 8772:  fe80::eb53:...%15, fe80::583f:...%3, ::1, ::, 
           192.168.55.103, 127.0.0.1  : 5353                          (6 bindings, incl. real LAN IPv4)
```
The first instance never bound the real LAN adapter (`192.168.55.103`) for mDNS at
all — only a single link-local IPv6 interface. This is a plausible explanation for
why "Discovered peers" showed nothing for the two legitimately-running instances to
find each other over the actual LAN: instance 1's discovery listener isn't present
on the interface instance 2 (or any real LAN peer) would announce on. Flagging as a
hypothesis for the Linux side to confirm against the `zeroconf`/interface-enumeration
code — not confirmed root cause.

---

## 7. NVIDIA GPU probe runs unconditionally on non-NVIDIA hardware

Every single launch, on this AMD-only machine:
```
WARNING maintenance.scanner: NVIDIA GPU query failed: NVML Shared Library Not Found
```
100% reproducible, every run, both instances. `Get-CimInstance Win32_VideoController`
confirms no NVIDIA adapter is present (`AMD Radeon(TM) Graphics`). The scanner
doesn't appear to gate the NVML probe behind actual NVIDIA-hardware detection.
Low severity (log noise only, observed), but trivial to reproduce on any non-NVIDIA
Windows box.

---

## 8. Thermals page: CPU temperature permanently blocked, Storage temperature never populates

User-driven repro: main window → System Overview → Thermals.

- **CPU Temperature** card shows: *"CPU temperature requires administrator
  privileges"* — permanently, with no in-app path to elevate/retry (app was not
  launched as admin, and there's no "Restart as administrator" affordance offered).
- **Storage Temperature** card shows: *"Waiting for the first sample"* and never
  progresses past that state.

Log search for `temp|therm|sensor|admin|storage` (case-insensitive) over the entire
log file: **zero matches** — same silent-failure pattern as #3/#4. Whatever is
blocking storage-temperature sampling, or gating CPU temperature on admin rights,
produces no log trace to diagnose from.

---

## 9. "Last refreshed" timestamp is frozen while the data behind it is clearly live

Repro: open System Overview, note the "Last refreshed: 12:04:58" label bottom-left,
wait 65+ seconds without touching anything, screenshot again.

Result: CPU (25.0% → 5.3%), Memory (66.3% → 65.2%, available GiB changed), Network
(0.00 B/s → 238.19 B/s down, 175.72 → 108.27 B/s up), Battery (85% → 82%) all
visibly updated — but **"Last refreshed: 12:04:58" never changed**, across a 65+
second wait. Preferences (Settings → Preferences → Scanning) confirms each card
polls independently and frequently (CPU 1s, Memory 5s, Network 1s, GPU 3s,
Battery/Storage 30s), so the per-card data is genuinely live. The single global
"Last refreshed" label is evidently wired to a different, one-shot "full scan"
completion event that only fires once at startup and never again — it does not
track the independent per-card refresh loops that actually update the numbers.

**Impact:** the timestamp is actively misleading — a user has no reliable way to
tell whether the dashboard is actually live or stalled, since the one indicator
meant to answer that question is itself stuck.

## 10. App exposes no accessible UI tree to Windows (UI Automation / assistive tech)

Using `System.Windows.Automation` against the main window (`ProcessId 14212`):
`FindAll(Descendants, TrueCondition)` returns **39 elements, all `ControlType.Pane`**
— zero buttons, zero text, zero named controls, despite the window visibly
containing many buttons, links, labels, and form fields (confirmed via
screenshots). This means the UI is rendered inside an embedded web/canvas surface
with accessibility not exposed to the OS at all.

**Impact:** the app is unusable with a screen reader or any UIA-based
assistive/automation tooling on Windows — not just a test-automation inconvenience,
a real accessibility gap.

## 11. Capability list text is clipped, not wrapped, in "All Systems"

Settings → All Systems → the "This System" machine row lists capabilities as a
single unwrapped line that runs off the right edge of its container and is cut off
mid-word: `..., Remote Management, Storage Re` (truncated, presumably
"Storage Read/Storage Removal/similar"). No ellipsis, no wrap, no horizontal
scroll affordance in that card — content is simply clipped by the window edge.

## 12. Local machine identity is presented inconsistently between pages

- All Systems → "This System" row: `Local · Online · Coordinator · DESKTOP-0C2C5H3
  · Local · Trusted · ...` — correctly shows the real Windows hostname.
- Nodes & Connections → Discovered peers (see finding #5, earlier session): a
  peer card labeled bare **"This System"**, no hostname shown at all, with a
  Node ID that did not match this machine's own `local_node_id`.

Same display string ("This System") is used for two different concepts —
"this is genuinely your local install" (All Systems) vs. "some discovered peer
that might be on the same machine" (Nodes & Connections) — with no hostname
disambiguation in the latter. This is the same confusable-identity issue as #5,
now confirmed from the trustworthy side (All Systems) as well.

## 13. Two legitimate, simultaneously-running instances never discover each other

With PID 14212 and PID 8772 both running normally (no crashes, both logging
"Network discovery active") for 10+ minutes side by side on the same machine,
Nodes & Connections still reports **"Status: Running - no peers found"** /
"Discovery running - 0 peers found" on both. Consistent with finding #6
(inconsistent mDNS interface binding) — the two processes' discovery listeners
are plausibly not reachable from each other's bound interfaces.

---

## Summary table

| # | Finding | Reproducible | Logged? |
|---|---|---|---|
| 1 | `--help`/`--version`/any flag ignored, launches GUI, hangs forever | Yes, 3/3 | No |
| 2 | No single-instance guard; shared node identity across processes | Yes | Partially (id logged, collision not) |
| 3 | Peer listener not actually bound to advertised port; warning silenced in 1.6.0.5 | Yes | No (was logged in 1.6.0.3) |
| 4 | Pairing fails with generic error, no log entry | Yes (user-driven) | No |
| 5 | Discovered peer mislabeled "This System" with mismatched Node ID | Yes | No |
| 6 | Inconsistent mDNS interface binding between instances | Yes | No |
| 7 | Unconditional NVIDIA NVML probe fails noisily on AMD-only box | Yes, every launch | Yes (WARNING) |
| 8 | Thermals: CPU temp permanently blocked, storage temp never samples | Yes (user-driven) | No |
| 9 | "Last refreshed" timestamp frozen while underlying data is live | Yes, 65s+ wait confirmed | No |
| 10 | No accessible UI tree exposed (UI Automation sees 39 unlabeled panes only) | Yes | N/A |
| 11 | Capability list text clipped mid-word, no wrap/ellipsis, in All Systems | Yes | N/A |
| 12 | "This System" label reused for both the real local install and an unrelated discovered peer | Yes | No |
| 13 | Two live, healthy instances never discover each other after 10+ min | Yes | Partially (INFO only, no error) |

## Suggested triage order for the Linux side

Per the project's testing protocol (`WINDOWS-TESTING-PROTOCOL.md`), pick the
**first broken boundary** rather than fixing everything at once. #1 (CLI entry point
ignoring argv) is the most isolated, most portable, and most likely to have a
Linux-runnable regression test (invoke the console-script entry point with
`--help`/`--version` and assert it prints and exits — no Windows-specific
behavior involved). Recommend starting there, since it's also what's polluting the
network-discovery state behind #2/#4/#5.
