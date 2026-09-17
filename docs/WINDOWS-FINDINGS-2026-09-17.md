# Windows Runtime Findings — system-analyzer 1.6.0.5 (+ 1.6.0.7 retest)

Machine: DESKTOP-0C2C5H3 (Windows 11 Home 10.0.26200), AMD Radeon GPU (no NVIDIA).
Installed via `irm https://raw.githubusercontent.com/20204166/exp/main/install/install-online.ps1 | iex`
(wheel: `system_analyzer-1.6.0.5-py3-none-any.whl`, upgraded from 1.6.0.3 already on the machine).
Log file: `C:\Users\BTN17\AppData\Local\system-analyzer\system-analyzer.log`
State dir: `C:\Users\BTN17\AppData\Roaming\system-analyzer\` (`cluster.json`, `cluster-history.sqlite3`, `peer-tls.{crt,key}`)

All findings below are reproduced on this physical Windows machine using the installed
wheel only — no source was cloned or edited.

**2026-09-17, PHASE 12D-W retest:** wheel `system_analyzer-1.6.0.7-py3-none-any.whl`
(SHA-256 `b54ccb0f50b8ff0c70c8adb1986a37ba24b4cbbe250405ee6bd09ad0c5d438f5`), built from
Linux fix commit `38e52c9` (argparse) + test commit `723840c`, installed via the same
online installer and confirmed via `pip show system-analyzer` → `Version: 1.6.0.7`.
Findings #1 and #2 below now carry a **Retest — 1.6.0.7** subsection each; the original
1.6.0.5 failure text is left unchanged as historical evidence.

**2026-09-17, PHASE 12E Linux repair:** wheel `system_analyzer-1.6.1.0-py3-none-any.whl`
(SHA-256 `2d68d4194de5c94ea67239dc802e41dd30085b1bd4531d8b9d8fff621910aaf0`), single-instance
guard for finding #2.  Windows retest pending.

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

### Retest — 1.6.0.7 (2026-09-17, PHASE 12D-W)

```powershell
system-analyzer --help
system-analyzer --version
system-analyzer --totally-bogus-flag-xyz
```

| Command | Exit code | Elapsed | Output | GUI? | Lingering process? |
|---|---|---|---|---|---|
| `--help` | 0 | 2.05s | `usage: system-analyzer [-h] [--version]` + description + options | No | None |
| `--version` | 0 | 1.06s | `system-analyzer 1.6.0.7` | No | None |
| `--totally-bogus-flag-xyz` | 2 | 1.06s | `system-analyzer: error: unrecognized arguments: --totally-bogus-flag-xyz` | No | None |

Process check after each command (`Get-Process ... python\|system-analyzer`)
returned **empty** every time — no launcher stub, no python child, no window.

**PHYSICAL RESULT: PASS.**

- Initial physical wheel: `1.6.0.5`
- Initial result: **FAIL** (argv ignored entirely, GUI launched and hung on all three commands — see above)
- Linux fix: commit `38e52c9`
- Retest wheel: `system_analyzer-1.6.0.7-py3-none-any.whl`
- Retest SHA-256: `b54ccb0f50b8ff0c70c8adb1986a37ba24b4cbbe250405ee6bd09ad0c5d438f5`
- Physical result: **PASS**

Finding #1 is physically closed on 1.6.0.7. Original 1.6.0.5 failure evidence above
is preserved as-is, not rewritten.

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

### Retest — 1.6.0.7 (2026-09-17, PHASE 12D-W)

Procedure per the physical retest plan: confirmed zero lingering processes after
the finding-#1 retest, launched exactly one normal `system-analyzer` (no args),
confirmed clean single-instance startup, then launched a second normal
`system-analyzer` (no args) while the first was still running. No state files were
modified by hand at any point.

| | First instance | Second instance |
|---|---|---|
| python PID | 14208 | 4432 |
| launcher PID | 8788 | 12080 |
| StartTime | 12:55:47 | 12:56:01 |
| Window title | System Analyzer | System Analyzer |
| Responding | True | True |
| Alive after both launches | Yes | Yes |

Both processes are healthy GUI instances — **no single-instance guard, no
redirect-to-existing-instance behavior**. Log evidence, both instances:
```
2026-09-17 12:55:51 INFO maintenance.components.network_discovery: Network discovery active for node-b31a0913e76db7c60cb7c6ec82313660
2026-09-17 12:56:04 INFO maintenance.components.network_discovery: Network discovery active for node-b31a0913e76db7c60cb7c6ec82313660
```
Identical node id on both lines, matching `cluster.json`'s `local_node_id`
(`node-b31a0913e76db7c60cb7c6ec82313660`) — confirmed both instances read the same
`local_node_id` from the same shared state directory
(`C:\Users\BTN17\AppData\Roaming\system-analyzer\`; only one `cluster.json`, one
`cluster-history.sqlite3` exist on this machine, no per-PID/per-instance copies).
Independent advertisement/discovery was not further exercised, per the "STOP" rule
below.

**PHYSICAL RESULT: FINDING #2 REMAINS REPRODUCED on 1.6.0.7.**

Per plan: STOPPING here. Not continuing to listener-port repair, mDNS adapter
repair, pairing repair, or "This System" labeling repair (findings #3–#6, #12–#13)
until this is resolved on Linux, since two processes owning the same persisted
node identity invalidates clean network testing of those other findings. Both test
instances were closed after evidence collection (no state files modified).

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

**Root-cause theory above corrected by the 1.6.0.7 retest — see below: the original
"leftover killed process" explanation does not hold up.**

### Retest — 1.6.0.7 (2026-09-17, user-driven + independently confirmed)

Fresh session: exactly **one** `system-analyzer` process was running (PID
8584/13680, launched clean, no prior `--help`/`--version`/bogus-flag instances this
session). The user opened Nodes & Connections and clicked **Pair** on the
"This System" discovered peer themselves; result was identical:
**"Target did not provision the peer grant."** User confirmed: *"still dud[n't]
work."*

Independently verified before and after:
- `Get-Process` (broad match `python|system.analyzer|pythonw`): only PID 8584/13680.
- `Get-ScheduledTask` filtered for system-analyzer/python: **no matches**.
- `Get-Service` filtered for system-analyzer/python: **no matches**.
- `system-analyzer.log`: the running instance logged only its own real node id
  (`node-b31a0913e76db7c60cb7c6ec82313660`) — **zero log lines** mentioning
  discovery or the `f...73f51b` peer, and zero new lines for the failed pair
  attempt (same silent-failure pattern as before).

The ghost peer itself: still labeled "This System", still Node ID
`node-f...73f51b` — **the exact same node-id suffix seen during the 1.6.0.5
session roughly 50 minutes and one wheel upgrade earlier** — but now advertising
on a different port (`36161` vs. the earlier `43737`).

**This contradicts the original root-cause theory.** A leftover killed process from
the earlier `--help`/`--version`/bogus-flag testing cannot explain a peer that:
(a) survived a full app version upgrade (1.6.0.5 → 1.6.0.7) and multiple full
process restarts/kills in between, and (b) is being discovered by a session with no
other local process, scheduled task, or service found anywhere on the machine.
The `f...73f51b` identity is coming from something this machine cannot see with
normal PowerShell process/task/service inspection — possibly a genuinely separate
device on the LAN, a stale multicast/mDNS cache entry somewhere in the network path
(router, another host), or a component of the app that persists independently of
the GUI process lifecycle. **Flagging for the Linux side to investigate directly
rather than assuming the earlier theory** — do not carry the "leftover test
process" explanation forward as fact.

**PHYSICAL RESULT: pairing still fails identically on 1.6.0.7. Not fixed (expected —
commit 723840c targeted finding #1 only). Root cause is less understood than
previously written, not more — see correction above.**

---

## 5. Discovered peer mislabeled "This System" despite a different Node ID

The peer in #4 is shown under the heading **"This System"** in the Discovered peers
list, but its Node ID does not match this machine's actual `local_node_id`. The
real Windows hostname is `DESKTOP-0C2C5H3`, not "This System" — so the label isn't
derived from the hostname either. This looks like a same-machine/loopback heuristic
that doesn't actually verify identity, so a user could be misled into pairing with an
untrusted or stale peer while believing it's their own instance.

### Retest — 1.6.0.7 (2026-09-17)

Unchanged: same "This System" label, same mismatched Node ID (`node-f...73f51b`),
now on port `36161` instead of `43737` (see #4 retest for full detail on why this
matters — the peer's persistence across an app upgrade rules out the "stale local
test process" theory this finding originally leaned on). **Not fixed, not
expected to be** (out of scope for commit 723840c).

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

### Retest — 1.6.0.7 (2026-09-17)

Full page captured this time (previous session only screenshotted a partially
scrolled view). Confirmed layout top-to-bottom: **Cpu Temperature**, **Gpu
Temperature**, **Storage Temperature**, **Battery Temperature**, **Recent thermal
events**.

- **Cpu Temperature:** unchanged — *"CPU temperature requires administrator
  privileges"*, permanently, no elevation affordance.
- **Gpu Temperature:** *"Waiting for the first sample"* — never progresses (new
  card not previously screenshotted in the 1.6.0.5 pass; same stuck state).
- **Storage Temperature:** unchanged — *"Waiting for the first sample"*, never
  progresses.
- **Battery Temperature:** unchanged — *"Waiting for the first sample"*, never
  progresses.
- **Recent thermal events:** *"No recent thermal events"* (new section not
  previously captured; consistent empty/inactive state, not obviously broken on
  its own).

Log search repeated for `temp|therm|sensor|admin` (case-insensitive) after visiting
this page on 1.6.0.7: **zero matches**, same as 1.6.0.5.

**PHYSICAL RESULT: unchanged / not fixed** (expected — commit 723840c targeted
finding #1 only, not thermals).

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

---

## Finding #1 — Repair log

**PHYSICAL INITIAL (wheel 1.6.0.5):** FAIL — `--help`/`--version`/any flag launched full GUI and never exited.

**Root cause:** `main.main()` called `AppWindow()` unconditionally; `sys.argv` was never inspected.

**Fix (commit 38e52c9 / wheel 1.6.0.7):**
`main._build_arg_parser()` returns an `argparse.ArgumentParser` with `--version` wired to `action="version"`.
`main.main()` calls `_build_arg_parser().parse_args()` as its first statement — before `setup_logging()`, before `AppWindow()`, before any network/state bootstrap.

**Linux regression tests added (`tests/test_logging_setup.py`):**
- `EntryPointArgParsingTests` — parser in isolation: exit codes, version string contains `__version__`
- `EntryPointEndToEndTests` — `main.main()` with `AppWindow` mocked: asserts not-called for help/version/unknown; called-once for no-args

**Linux clean-venv smoke test (wheel 1.6.0.7):**

| Command | Output | Exit |
|---|---|---|
| `system-analyzer --help` | usage text | 0 |
| `system-analyzer --version` | `system-analyzer 1.6.0.7` | 0 |
| `system-analyzer --totally-bogus-flag-xyz` | `error: unrecognized arguments: ...` | 2 |

**Wheel:** `system_analyzer-1.6.0.7-py3-none-any.whl`
**SHA-256:** `b54ccb0f50b8ff0c70c8adb1986a37ba24b4cbbe250405ee6bd09ad0c5d438f5`

**Windows retest:** NOT VERIFIED — install 1.6.0.7 on Windows and run the three commands above.

---

## Finding #2 — Linux fix in progress (Phase 12E)

Single-instance guard absent.  Still independently reproducible (confirmed REPRODUCED on 1.6.0.7 — see retest in the Finding #2 section above).

### Phase 12E Linux repair (2026-09-17)

**Fix commit:** _pending — see Phase 12E commit_
**Fix wheel:** `system_analyzer-1.6.1.0-py3-none-any.whl`
**SHA-256:** `2d68d4194de5c94ea67239dc802e41dd30085b1bd4531d8b9d8fff621910aaf0`

**Mechanism:** `maintenance/instance_lock.py` (new module) — OS-held exclusive
advisory lock on the profile state directory (`%APPDATA%\system-analyzer\system-analyzer.lock`
on Windows).  POSIX uses `fcntl.flock`; Windows uses `msvcrt.locking`.  Both
paths release automatically on process termination including crashes (OS holds
the lock on the file descriptor; fd closed on death → lock released).

**Lock acquisition point:** `main.main()` — after `argparse.parse_args()` (so
`--help`/`--version` still work while a runtime instance holds the lock), before
`AppWindow()` construction (so no mutable state is touched by the second launch).

**Second launch behavior:** prints `System Analyzer is already running.` to
stderr, exits with code 1.  `AppWindow` is never constructed; `cluster.json`
is never written; mDNS and the listener are never started.

**Linux automated evidence:**

| Test class | Label | Count |
|---|---|---|
| `InstanceLockAcquireTests` | UNIT | 5 |
| `InstanceLockSubprocessTests` | REAL OS LOCK — Linux | 2 |
| `WindowsLockBranchTests` (test_instance_lock.py) | UNIT / EMULATED WINDOWS BRANCH | 3 |
| `WindowsInstanceLockBranchTests` (test_cross_platform_branches.py) | UNIT / EMULATED WINDOWS BRANCH | 3 |
| `EntryPointEndToEndTests` additions | UNIT | 4 |

Subprocess tests (`InstanceLockSubprocessTests`) spawn real child processes and
exercise the OS-level flock exclusion and crash-recovery path.  These are
`REAL OS LOCK ON LINUX`, not physical Windows evidence.

**Windows retest required:** install `system_analyzer-1.6.1.0-py3-none-any.whl`
on DESKTOP-0C2C5H3, launch two no-arg GUI instances, confirm second launch prints
`System Analyzer is already running.` and exits immediately, confirm first instance
remains alive.  Then kill the first instance forcefully and confirm a fresh launch
succeeds (crash-recovery).
