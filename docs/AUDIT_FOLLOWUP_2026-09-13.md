# Architecture Audit Follow-Up — 2026-09-13

Plain-language companion to `docs/SYSTEM_ARCHITECTURE_REVIEW.md`. That document is the full
evidence-dense technical audit; this one answers "what did you actually fix, what did you
decide to leave alone, and why" in normal language, so it's easy to find later without
re-reading the whole review.

---

## What was fixed in this pass

Four of the audit's findings were mechanical, low-risk bugs with one clear correct fix. All four
are done, tested, and verified (each new/changed test was deliberately made to fail first by
temporarily breaking the fix, to prove it actually catches the problem, then restored):

### 1. Diagnostics page's "Copy diagnostics" button (Finding A-1)

The Diagnostics page had a live `ButtonCoordinator` (the shared system that gives every button a
stable, addressable ID) plumbed into it, but its one button never actually registered with it —
same class of bug as an earlier gap on the Thermals page this session, just not yet caught by the
test suite built to catch that class of bug. Fixed: the button now registers as
`"diagnostics:copy"`, and the wiring test suite (`test_page_wiring_consistency.py`) now checks for
it so it can't silently regress.

### 2. Thermal telemetry's `record_scan` method (Finding D-2)

There are two ways temperature readings get fed into the system's thermal-tracking object:
`record_summary` (the one actually used, every time) and `record_scan` (an alternate entry point
with zero current callers anywhere in the app — dead code, but still part of the public API).
`record_summary` correctly resets its "how many empty readings in a row" counter whenever a real
reading comes in; `record_scan` didn't. Since nothing calls `record_scan` today this had zero
real-world effect, but it was a latent inconsistency in the class's own contract. Fixed for
symmetry, with a test proving the counter now resets correctly either way.

### 3. Remote protocol capability/permission map (Finding F-1)

Every remote operation (like "read the dashboard" or "force-quit a process") is gated by two
hand-written lookup tables: one saying what *capability* the target node needs, one saying what
*permission* the caller needs. Nothing previously checked that these two tables stay in sync with
each other, or that every declared capability is actually used by at least one operation — the
exact same "hand-maintained list can silently drift" risk this session already found and fixed
once for the CPU/Memory/GPU dashboard dispatch. Added a test mirroring that existing pattern.

### 4. Pairing/grant secrets stored in `cluster.json` (Finding G-1)

**Note on this one specifically**: on this machine, the file was *already* private
(`-rw-------`, i.e. owner-read-write-only) purely as a side effect of how the atomic-write helper
creates its temporary file — not because anything explicitly asked for that. That's real
protection today on Linux/macOS, but it was implicit and undocumented, and nothing enforced it. I
added an explicit `chmod 0600` after every save, matching the same treatment the adjacent TLS
private key already gets, so the protection is guaranteed by the code rather than by an
implementation detail of a library function, and added a test that checks the file's permissions
directly after a save.

**All four fixes, plus their new/updated tests, pass together and pass the full 1456-test suite**
except for one unrelated pre-existing issue (see below) that has nothing to do with this work.

---

## Something unrelated found while testing

Two commits landed on `main` from outside this conversation
(`bf5f075 docs: add guard clause simplification guidance`,
`c93a25e refactor: isolate network scanner responsibility`) between this session's last push and
now. The refactor moved network-card scanning code into a new file,
`maintenance/scanner_support/network.py` — but the wheel currently sitting in `dist/` was never
rebuilt afterward, so it's missing that file. Anyone installing from that wheel right now would hit
an `ImportError` at startup. This is a real, currently-broken build artifact, not something this
session caused. Flagged to you separately in chat; not touched here unless you ask.

---

## PlacementPolicy — what it is, and why it's untouched

`maintenance/components/placement.py` is a fully built, tested **node picker**: given a
description of a job (what it needs, whether it can run anywhere or only on one specific machine,
roughly how much data moving it would cost), it scores every known node — trusted? online? has the
right capability and permission? how loaded? how fresh is its last report? how far away
(latency)? — and returns either the single best node to run that job on, or a clear rejection
reason if none qualify.

**Nothing in the app calls it.** There is no point today where the app itself decides which node
should run a piece of work — every scan, dialog, and action runs on whatever node the user
manually selected. The engine is real and correct; it's just never bolted into anything. Wiring it
up means choosing a specific action that should get "auto-pick the best node" behavior instead of
"whatever the user clicked" — that's a product decision (which job? does it override manual
selection or only apply when nothing is selected? what happens if the "best" node isn't the one
the user expected?), not a bug fix, so it hasn't been implemented pending that decision.

**Status: open.** No code changed for this finding. If a decision is made later, the natural
places to look are `AppCoordinator.choose_placement()` (the entry point already exposed) and
`maintenance/ui/cluster_page.py`'s "Remove job" button (`on_remove_job`) as the nearest existing
example of a job-lifecycle action in the UI — an "Assign job" counterpart doesn't currently exist
either.

---

## Cluster invites — left as-is, by request

`ClusterState.create_invite()` (mint a one-time join token) has no button or menu anywhere that
calls it, even though the *receiving* half (`consume_invite`) is fully wired on the machine being
joined. Building this out for real would mean two new flows: "Create Invite" (mint + display/copy
a token) on one machine, and a brand-new "Join via Invite" flow on the other (there's currently no
UI at all for a machine to consume an invite it was given — only the low-level wire handler
exists). That's a genuine two-sided feature, not a small fix.

**Decision: leave as-is.** Direct discover-and-Pair (the "Pair" button on a discovered peer) is
the normal, fully-working way to establish trust between two machines on the same LAN today, and
covers the normal case. Invites stay implemented-but-unexposed.

---

## Two UX judgment calls — documented, not changed

These aren't bugs; they're places where the current behavior is a legitimate design *choice* that
just happens to be inconsistent or asymmetric, and picking a different choice is equally valid.
Recorded here rather than changed in code.

### D-1 — Thermal "unsupported" display is inconsistent across components

When a sensor's temperature reading settles into "unsupported" (the hardware genuinely doesn't
expose it), the Thermals page treats Battery differently from CPU/GPU/Storage:

- **CPU / GPU / Storage**: the entire graph section for that component disappears. If every
  component ends up unsupported, the page shows one generic "No supported temperature sensors
  detected" message instead.
- **Battery**: the graph section stays visible and shows an "unsupported" state directly, because
  the battery card is coded to always report itself as capability-`SUPPORTED` for any physically
  present battery, regardless of whether it has a temperature sensor.

Neither behavior is wrong on its own — hiding an unsupported sensor entirely avoids clutter;
showing a placeholder tells the user "we looked, there's genuinely nothing here" instead of
silently omitting a section they might expect. They're just not the *same* choice, and nothing
currently makes that an intentional design decision versus an accident of how the battery card
happens to be coded. Left unchanged pending a decision on which behavior all four components
should share.

### A-2 — "All Systems" (cluster) page always returns to Dashboard

The cluster page is reachable from two places — the Dashboard's "All Systems" button, and the
Settings hub's "All Systems" card — but its back button always returns to Dashboard, never to
Settings. Every other page reachable from the Settings hub returns to the Settings hub when you
hit back; this is the one exception. It could be intentional (arguably "All Systems" is more of a
dashboard-adjacent view than a true settings page), or it could just be an oversight, since fixing
it "properly" (remembering which page you came from) is a small but real added-state change, not a
one-line default swap. Left unchanged pending a decision on the intended behavior.

---

## Quick status table

| Finding | What it is | Status |
|---|---|---|
| A-1 | Diagnostics "Copy" button not registered with ButtonCoordinator | **Fixed** |
| D-2 | `record_scan` doesn't reset empty-read counter | **Fixed** |
| F-1 | No drift test for remote capability/permission maps | **Fixed** |
| G-1 | Pairing secrets file permissions not explicit | **Fixed** |
| E-2 | PlacementPolicy has no caller | **Open — awaiting your decision on a trigger point** |
| E-3 | No UI to create/consume cluster invites | **Left as-is, by your request** |
| D-1 | Thermal "unsupported" shown inconsistently across components | **Left as-is, documented** |
| A-2 | Cluster page back button always goes to Dashboard | **Left as-is, documented** |
| B-1 | Manual scan uses a different background-execution model than everything else | **Not addressed this pass** — lowest priority per the original audit, not requested |
