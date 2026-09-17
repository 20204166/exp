# Windows Runtime Findings — system-analyzer 1.6.0.5 (+ 1.6.0.7, 1.6.1.0 retests)

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

### Retest — 1.6.1.0 (2026-09-17, PHASE 12E-W)

wheel: `system_analyzer-1.6.1.0-py3-none-any.whl`
SHA-256: `2d68d4194de5c94ea67239dc802e41dd30085b1bd4531d8b9d8fff621910aaf0`

Installed via the normal online installer; `system-analyzer --version` confirmed
`system-analyzer 1.6.1.0` before proceeding.

**CLI regression (must still hold from Phase 12D):**

| Command | Exit | GUI? | Lingering process? |
|---|---|---|---|
| `--help` | 0 | No | No |
| `--version` | 0 | No | No |
| `--totally-bogus-flag-xyz` | 2 | No | No |

Unchanged — regression clean.

**First launch:** launcher PID `6888`, runtime PID `15028`, both started
`13:52:13`, responding, GUI up within the 5s check window.

**Second no-arg launch (first instance still running):**
```
exit code: 1
stderr:    System Analyzer is already running.
elapsed:   1.09s
```
No second GUI appeared. Process check immediately after: still only PID
15028/6888 — no second python child, no second launcher, no hidden process.

**Network side-effect check:** log tail around the rejected launch shows exactly
one `Network discovery active for node-...` line (13:52:16, matching the surviving
first instance's own startup) — no second discovery/listener/advertisement event
from the rejected process.

**Node identity check:** `cluster.json.local_node_id` unchanged
(`node-b31a0913e76db7c60cb7c6ec82313660`); no duplicate `cluster.json`/
`cluster-history.sqlite3`/TLS files created. New artifact observed:
`system-analyzer.lock` (first seen `13:52:26`) — the single-instance lock file
introduced this phase. Not modified or deleted at any point during this test.

**CLI while GUI is running:** `--help` and `--version` both still returned exit 0
with correct output, no "already running" message, GUI remained healthy
(single instance, responding) throughout.

**Normal shutdown → relaunch:** `Process.CloseMainWindow()` on the runtime PID
returned `True`, process exited within 15s. Relaunch immediately after
succeeded normally (new PID pair `13724`/`7956`, no rejection).

**Force-kill → relaunch (no manual lock deletion):** `Stop-Process -Force` on
runtime PID `13724`. All processes gone immediately after. Lock file
(`system-analyzer.lock`) remained physically present on disk (pathname survived,
untouched by this test). Immediate relaunch with **no manual intervention**
succeeded (new PID pair `11572`/`12024`) — proves ownership is OS-held, not
stale-file-held, matching the "file may survive a crash, ownership may not" model.

**Second-launch rejection after crash recovery:** repeated against the recovered
instance — exit 1, `System Analyzer is already running.`, no new process, original
recovered instance (PID 11572/12024) untouched.

**Finding #2 pass criteria:**

| # | Criterion | Result |
|---|---|---|
| A | First GUI starts normally | PASS |
| B | Second no-arg launch: no GUI / already-running stderr / exit 1 / no lingering runtime | PASS |
| C | First runtime remains healthy | PASS |
| D | `--help`/`--version` still work while GUI running | PASS |
| E | Fresh launch succeeds after normal close | PASS |
| F | Fresh launch succeeds after force-kill, no manual lock deletion | PASS |

**PHYSICAL RESULT: PHYSICAL PASS. Finding #2 is physically closed on 1.6.1.0.**
Original 1.6.0.5/1.6.0.7 failure evidence above preserved unchanged.

All instances closed after this test. Per the retest plan, network validation
(pairing, thermals, listener, mDNS) resumes from a clean single-runtime
environment next — old evidence gathered under duplicate-instance conditions is
not assumed to still apply and is being rediscovered fresh, not patched onto.

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

**Fix commit:** `4814049`
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

**Windows retest — DONE, PHYSICAL PASS.** See the "Retest — 1.6.1.0 (PHASE 12E-W)"
subsection under Finding #2 earlier in this document for full evidence (PIDs, exit
codes, timings, six-criteria pass table). This "Windows retest required" note
above is stale as of that retest; left in place for chronology rather than edited,
per prior agreement not to silently rewrite externally-authored content.

---

## PHASE 12E-W — Clean single-runtime network/thermals baseline (2026-09-17, wheel 1.6.1.0)

Per the retest plan: old network evidence (findings #3–#6, #12–#13) was gathered
while duplicate-instance ownership was still possible, so it is not assumed valid.
This section is a **fresh** reproduction from a guaranteed single-runtime
environment (Finding #2 confirmed PASS immediately beforehand; only one process,
PID 1216/14788, running for the whole of this section) — not a patch onto old
evidence.

**Thermals:** unchanged from both prior versions. Cpu Temperature still *"CPU
temperature requires administrator privileges"* (permanent, no elevation path);
Gpu/Storage/Battery Temperature still *"Waiting for the first sample"*
indefinitely. Confirmed reproduced identically on 1.6.1.0 from a clean single
instance — not an artifact of the earlier duplicate-instance sessions.

**Pairing / Discovery — behavior has changed, and not obviously for the better:**
on this clean instance, Nodes & Connections shows **"Status: Running - no peers
found"** / **"Discovered peers: No peers discovered yet"**, sustained for 100+
seconds of observation (checked at ~0s, ~40s, ~100s after opening the page; log
file gained zero new relevant lines in that window beyond this instance's own
periodic discovery/NVML entries). This is different from both the 1.6.0.5 and
1.6.0.7 sessions, where a peer labeled "This System" (Node ID `node-f...73f51b`)
was already visible within the first screenshot taken.

**This means the previously-reproduced pairing failure (findings #4/#5: "Target
did not provision the peer grant" against a mismatched-identity "This System"
peer) has NOT yet been re-reproduced from this clean instance** — there is
currently nothing in the Discovered peers list to attempt pairing against. This is
recorded as a genuine behavior difference, not assumed to mean the underlying bug
is fixed (Phase 12E's stated scope was the single-instance lock, not discovery/
pairing) and not assumed to mean it's still broken in the same way either. Two
explanations are open and unconfirmed:
1. The `f...73f51b` ghost peer's source (still unidentified — see the 1.6.0.7
   retest note under finding #4) happens not to be broadcasting/reachable at this
   moment, independent of anything this wheel changed.
2. Something incidental to a longer-running clean single-instance session (vs. the
   rapid multi-instance churn of earlier sessions) changed what gets discovered.

**Open question for the user:** if a pairing failure was observed during this same
session, it was most likely against one of the earlier PHASE 12E-W lock-test
instances (PIDs 15028/6888, 13724/7956, or 11572/12024) before they were closed —
those were not individually checked for Nodes & Connections state before closing.
Not claiming pairing is fixed on 1.6.1.0; the clean repro simply hasn't caught the
same failure yet. Next step, pending user direction: extend the observation window
and/or check whether the ghost peer reappears with more elapsed time, rather than
prematurely marking either PASS or FAIL.

---

## PHASE 12F — Controlled two-node discovery/listener validation (2026-09-17, both nodes 1.6.1.0)

**Purpose:** replace speculative single-node evidence with a controlled two-node
baseline.  Evidence boundary: prove each stage in order (single process per node →
known NodeIds → actual listeners → direct TCP → mDNS discovery → identity match →
TLS → Pair → authenticated hello) before diagnosing the next.

---

### PHASE 12F-L — Linux identity resolution (2026-09-17)

**Context:** Windows's first controlled observation found NodeId
`node-983364764039f9e6625e687273710909`, not the previously-recorded
`node-ff37fa18b5d28f2343ab617f8773f51b`, with TLS fingerprint
`1a7b:7cc8:e529:c7f7:2e92:4ce7:51d8:ce0f:54bf:b526:30ca:5fe0:263d:cd5a:c340:adc7`.
This pass resolves the discrepancy before permitting another Pair.

#### LINUX RUNTIME

| Field | Value |
|---|---|
| Version | `1.6.1.0` |
| PID | `3220` |
| Command | `/home/btn17/Downloads/exp/.venv/bin/python /home/btn17/.local/bin/system-analyzer` |
| Start time | `2026-09-17 15:49:58` |
| Resolved state root | `/home/btn17/.config/system-analyzer/` |
| `cluster.json` `local_node_id` | `node-983364764039f9e6625e687273710909` |
| `cluster_id` | `local-cluster` |
| Actual listener bind | `0.0.0.0:43281` |
| Actual listener port | **43281** |

Only one System Analyzer process on Linux; no second runtime, no second profile
directory.

#### LINUX TLS

| Field | Value |
|---|---|
| Certificate path | `/home/btn17/.config/system-analyzer/peer-tls.crt` |
| Cert created | `2026-09-10 15:30` (unchanged since creation) |
| Canonical TLS fingerprint (SHA-256/DER) | `1a7b:7cc8:e529:c7f7:2e92:4ce7:51d8:ce0f:54bf:b526:30ca:5fe0:263d:cd5a:c340:adc7` |
| Matches Windows-observed fingerprint | **YES — exact match** |

#### LINUX DISCOVERY

| Field | Value |
|---|---|
| Zeroconf-visible addresses | `['100.85.0.1', '192.168.55.107', '10.2.0.2', '127.0.0.1']` |
| UDP 5353 bindings (PID 3220) | `192.168.55.107:5353`, `10.2.0.2:5353`, `127.0.0.1:5353`, `100.85.0.1:5353` (4 IPv4 bindings); plus `*`, `::`, `[::1]`, link-locals on IPv6 |
| Advertised service instance | `node-983364764039f9e6625e687273710909._system-analyzer._tcp.local.` |
| Advertised `id` (NodeId) | `node-983364764039f9e6625e687273710909` |
| Advertised hostname | `m75-node1.local.` |
| Advertised port | **43281** |
| Advertised addresses | `10.2.0.2` (VPN — listed **first**), `100.85.0.1` (VPN), `192.168.55.107` (LAN — listed **third**) |
| Advertised `tls_fingerprint` | `1a7b:7cc8:e529:c7f7:2e92:4ce7:51d8:ce0f:54bf:b526:30ca:5fe0:263d:cd5a:c340:adc7` |
| Advertised `connectable` | `true` |

**VPN address ordering confirmed:** `10.2.0.2` (unreachable from Windows) is first
in the address list.  `window_discovery.py:1234` selects `candidate.addresses[0]`
when building the connection endpoint for a trusted-node endpoint sync — if Windows
picks the first address for the pair attempt, the connection would target an
unreachable VPN IP.  That said, the Windows pair attempt returned the structured
"Target did not provision the peer grant" response (not a connection error), which
implies the TCP connection did succeed — possibly because Windows tried multiple
addresses or the address ordering was different on the Windows resolver side.  The
`addresses[0]` selection is a confirmed code path, confirmed to pick a VPN address
first here, and is recorded as a separate finding candidate for the next pass.

#### PROFILE AUDIT

Only one System Analyzer profile directory exists:
`/home/btn17/.config/system-analyzer/`

`node-ff37fa18b5d28f2343ab617f8773f51b` — found only in log history:
`/home/btn17/.local/state/system-analyzer/system-analyzer.log`
(last appearance: `2026-09-17 14:50:34`).  Not present in any cluster.json or TLS
file.

`node-983364764039f9e6625e687273710909` — appears in current cluster.json and in
log history from `2026-09-17 15:01:48` onward.

#### IDENTITY CHANGE ROOT CAUSE

At `2026-09-17 15:01:45`:
```
WARNING maintenance.cluster: Unsupported cluster settings schema; using defaults
```

`ClusterStore._parse()` (`cluster.py:922-925`) rejects any `schema_version` not in
`(1, 2)`.  When it rejects, it returns `ClusterState()` — the no-arg default —
which has `local_node_id: str = "local"` (`cluster.py:661`).  The outer `load()`
then detects `local_node_id == "local"` (`cluster.py:850`) and calls
`generate_stable_node_id()`, producing `node-983364...`.  The TLS cert is generated
by a separate code path (`ensure_tls_material()`) and was NOT regenerated.

**The old cluster.json had a `schema_version` outside `(1, 2)` — most likely from
an experimental/newer source build.  When this version was loaded by the current
code, it silently discarded the `local_node_id` and generated a new one.**

This is an identity-persistence bug: `ClusterStore.load()` should preserve
`local_node_id` even when `schema_version` is unsupported.  The node's network
identity should not be tied to schema migration success.  This is noted for future
repair; per Phase 12F-L instructions, no production code is changed here.

#### CONSISTENCY CHECK

| Comparison | Result |
|---|---|
| `cluster.json NodeId` == `mDNS advertised NodeId` | **MATCH** — both `node-983364764039f9e6625e687273710909` |
| `mDNS advertised NodeId` == `Windows-discovered NodeId` | **MATCH** |
| `cluster.json NodeId` == `Windows-discovered NodeId` | **MATCH** |
| Actual Linux listener port == mDNS advertised port | **MATCH** — both `43281` |
| mDNS advertised port == Windows-discovered port | **MATCH** — both `43281` |
| Linux TLS fingerprint == mDNS advertised `tls_fingerprint` | **MATCH** |
| Linux TLS fingerprint == Windows-observed TLS fingerprint | **MATCH** |

All four identity sources (cluster.json, runtime log, mDNS advertisement,
Windows discovery) are coherent on `node-983364764039f9e6625e687273710909`.

#### CONCLUSION

**Windows-discovered peer IS the current m75-node1 Linux runtime — VERIFIED.**

The earlier `node-ff37...` record was stale: the cluster.json was regenerated today
at 15:01:45 due to an unsupported schema version.  The TLS cert survived
unchanged across that event (it is the stable cross-session identity anchor).

**Earlier Phase 12F doc note corrected:** the ghost-peer identification based on
NodeId suffix truncation (`f...73f51b` ≈ `f8773f51b`) was circumstantially correct
in attributing the peer to the Linux machine, but the specific NodeId it cited
(`node-ff37...`) was from an already-superseded cluster state.  The current
authoritative Linux NodeId is `node-983364764039f9e6625e687273710909`.

#### FIRST BROKEN BOUNDARY

No broken boundary at the identity/TLS/port layer — all consistent.  Two
unresolved items carried forward:

1. **VPN address ordering**: `addresses[0]` picks `10.2.0.2` (VPN, unreachable from
   Windows) before `192.168.55.107` (LAN).  Whether this caused the pair failure
   is unconfirmed — the "Target did not provision the peer grant" response suggests
   TCP succeeded, but address-selection behaviour on the Windows resolver side is
   not yet proven.

2. **Pair failure root cause**: the pair was attempted before this identity pass
   completed; the Linux approval dialog may have timed out (user was on Windows side,
   not watching the Linux screen).  A new controlled pair — with a user watching
   both screens simultaneously — is required to distinguish a human-timeout from a
   production defect.

**Production code changed: NO.**

---

### NODE A identity (Linux — m75-node1) — CORRECTED post Phase 12F-L

| Field | Value |
|---|---|
| Hostname | `m75-node1` |
| App version | `1.6.1.0` |
| **local_node_id (current)** | **`node-983364764039f9e6625e687273710909`** |
| local_node_id (historical, superseded) | `node-ff37fa18b5d28f2343ab617f8773f51b` (last seen 14:50:34, replaced by schema-fallback at 15:01:45) |
| cluster_id | `local-cluster` |
| LAN IPv4 | `192.168.55.107` (interface `enp2s0f0`) |
| VPN adapters present | `pvpnksintrf1` at `100.85.0.1/24` (ProtonVPN, **default route**); `proton0` at `10.2.0.2` |
| discovery_enabled | `True` |
| Listener port | **43281** (OS-confirmed, PID 3220) |
| mDNS advertised addresses | `10.2.0.2` (VPN, first), `100.85.0.1` (VPN, second), `192.168.55.107` (LAN, third) |
| TLS fingerprint | `1a7b:7cc8:e529:c7f7:2e92:4ce7:51d8:ce0f:54bf:b526:30ca:5fe0:263d:cd5a:c340:adc7` |

### NODE W identity (Windows — DESKTOP-0C2C5H3)

| Field | Value |
|---|---|
| Hostname | `DESKTOP-0C2C5H3` |
| App version | `1.6.1.0` |
| local_node_id | `node-b31a0913e76db7c60cb7c6ec82313660` |
| LAN IPv4 | `192.168.55.103` |
| Listener port | `0.0.0.0:50778` (OS-confirmed) |
| discovery_enabled | `True` |
| mDNS service type | `_system-analyzer._tcp.local.` |

### Phase 12F controlled experiment — IN PROGRESS

| Step | Status | Evidence |
|---|---|---|
| Single process — NODE A | **CONFIRMED** — PID 3220 only | `ps aux`, `ss -tlnp` |
| Single process — NODE W | **CONFIRMED** | Windows process check |
| Listener port — NODE A | **CONFIRMED** `43281` | `ss -tlnp` PID 3220 |
| Listener port — NODE W | **CONFIRMED** `50778` | Windows `Get-NetTCPConnection` |
| Advertised port == actual port — NODE A | **CONFIRMED** `43281` == `43281` | mDNS browse + `ss` |
| Advertised port == actual port — NODE W | PENDING | — |
| Direct TCP: Linux → Windows listener | PENDING | — |
| Direct TCP: Windows → Linux listener | PENDING | — |
| mDNS: NODE W sees NODE A | **CONFIRMED** — `node-983364...` seen on Windows | Windows Nodes & Connections |
| mDNS: NODE A sees NODE W | PENDING | — |
| Discovered NodeId matches expected — Windows sees Linux | **CONFIRMED** | `node-983364...` == cluster.json |
| Discovered NodeId matches expected — Linux sees Windows | PENDING | — |
| "This System" mislabel for remote node absent | PENDING — reclassify after next observation | — |
| Controlled Pair — both screens attended | PENDING — requires user watching both screens | — |
| Authenticated hello | PENDING | — |

---

## PHASE 12F-W — Windows-side evidence (2026-09-17)

Executed the Windows-only portions of the Phase 12F controlled plan. **No access
to the Linux machine from this session** — Part A (Linux zeroconf/listener/mDNS
prep), direct TCP from the Linux side, and Linux-side discovery observation could
not be performed here and still need to come from the Linux side or a separate
Linux-side session.

### Part B — NODE W prep (complete)

| Field | Value |
|---|---|
| Version | `system-analyzer 1.6.1.0` (confirmed via `--version`) |
| Runtime PID | `4020` (launcher `4624`), single instance confirmed, `MainWindowTitle` = `System Analyzer` |
| **WINDOWS_ACTUAL_PORT** | `50778`, bind `0.0.0.0` (`Get-NetTCPConnection -State Listen` filtered to PID 4020) |
| LAN adapter | `WiFi` → `192.168.55.103/24`, has default gateway — matches expected NODE W address |
| Other adapters | `Local Area Connection* 1` `169.254.99.193/16`, `Local Area Connection* 2` `169.254.87.51/16`, `Bluetooth Network Connection` `169.254.208.36/16` — all APIPA, no gateway, no VPN adapter present on Windows |

Part C (direct TCP) not yet performed — blocked on `LINUX_ACTUAL_PORT` from the
Linux side.

### Part D/F — discovery + pairing observation (2026-09-17, ~15:51)

On the same NODE W instance (PID 4020/4624, still the single confirmed runtime),
user opened Nodes & Connections and attempted Pair against a discovered peer. Full
evidence captured via the in-app "Details" panel:

```
Name: This System
Node ID: node-983364764039f9e6625e687273710909
Hostname: This System
Host: This System
Port: 43281
Pairing: pairing_failed
Target: (empty)
Role: (empty)
Permissions: (empty)
Identity status: (empty)
Identity fingerprint: cf1e:352f:367e:4111:a9c6:696c:2871:af2d:f65d:e0e9:6b69:3dc6:4c02:831d:4008:6a04
TLS fingerprint: 1a7b:7cc8:e529:c7f7:2e92:4ce7:51d8:ce0f:54bf:b526:30ca:5fe0:263d:cd5a:c340:adc7
```

UI error shown: **"Target did not provision the peer grant"** (same text as every
prior session).

**This does NOT match the documented Linux identity.** Per this document's own
PHASE 12F prep note above (line ~641), the expected Linux `local_node_id` is
`node-ff37fa18b5d28f2343ab617f8773f51b` (truncated suffix `...73f51b`). The NodeId
captured just now is `node-983364764039f9e6625e687273710909` (suffix `...710909`)
— a different value, not a truncation match. Per Part G of the Phase 12F-W plan,
this is recorded as an **unexpected peer**, not assumed to be Linux NODE A:

| NodeId | name | hostname | port | first seen | last seen |
|---|---|---|---|---|---|
| `node-983364764039f9e6625e687273710909` | This System | This System | 43281 | ~15:51 (this session, PID 4020) | ~15:52, status `pairing_failed` |

**Anomaly worth flagging before anyone trusts this as "the Linux node":** the TLS
fingerprint captured here (`1a7b:7cc8:e529:c7f7:...:cd5a:c340:adc7`) is
**byte-identical** to the TLS fingerprint captured in both the 1.6.0.5 session
(finding #4, port `43737`) and the 1.6.0.7 session (finding #4 retest, port
`36161`) — despite the displayed Node ID and port being different in all three
observations (`...73f51b`/43737, `...73f51b`/36161, `...710909`/43281 — note even
the *first two* sessions' node-id suffix as OCR'd from a truncated dialog may not
be as reliable as assumed; only this session's suffix was read from the untruncated
Details panel). A TLS certificate fingerprint is a cryptographic identity that
should not change across genuinely different remote devices or app restarts on the
same device with persisted keys; a self-reported `Node ID` string is comparatively
easy to regenerate. This is the opposite of what would be expected if these were
either (a) three consistent observations of the same real Linux node, or (b) three
different devices. It is flagged here, unresolved, rather than assumed to confirm
either the "phantom Windows artifact" theory or the "confirmed Linux node" theory.

**Supporting evidence, checked at time of capture:**
- `cluster.json` on Windows: `peer_grants: []`, `trusted_nodes: []` — the failed
  pairing left no trace here.
- `system-analyzer.log`: **zero new lines** since this instance's own startup
  (`14:47:11`), despite the discovery + pairing attempt happening over an hour
  later (~15:51–15:52). Same silent-failure pattern as findings #3/#4/#8.

**Status: UNRESOLVED, blocking further controlled pairing.** Per the plan's Part G
and the "do not pair with unknown peers" rule, this observation should not be
treated as either a reproduction or a non-reproduction of the documented
Linux-node pairing failure until the Linux side confirms what `local_node_id`
`m75-node1` is *currently* reporting in its own `cluster.json`. Open question sent
to the user: is `m75-node1` running right now, and does its current
`local_node_id` match `node-ff37fa18b5d28f2343ab617f8773f51b`,
`node-983364764039f9e6625e687273710909`, or neither?

No source code was changed during this phase. No further Pair attempts were made
against this or any other peer after this observation, pending clarification.
