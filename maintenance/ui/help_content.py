"""Canonical content for the in-app Help & Guide page.

This is the single owner of user-facing explanatory copy for System
Analyzer. Feature pages keep only short, operational text (status lines,
confirmation dialogs, safety warnings); the longer "why" and "how" belongs
here so it exists in exactly one place. Every claim below is grounded in the
current implementation, not aspirational or historical behaviour -- when
current code and older documentation disagreed, current code won.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class HelpSection:
    """One heading plus its explanatory paragraphs and optional bullets."""

    heading: str
    paragraphs: tuple[str, ...] = ()
    bullets: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class HelpTopic:
    """One browsable Help topic: a title, a one-line summary, and sections."""

    key: str
    title: str
    summary: str
    sections: tuple[HelpSection, ...]


HELP_TOPICS: tuple[HelpTopic, ...] = (
    HelpTopic(
        key="getting-started",
        title="Getting Started",
        summary="The normal first-use path, from install to your first scan.",
        sections=(
            HelpSection(
                heading="The usual path",
                bullets=(
                    "Install System Analyzer (see Installing System Analyzer).",
                    "Launch it -- the Dashboard opens showing your own machine.",
                    "Read the CPU, Memory, Storage, GPU, Network, and Battery cards.",
                    (
                        "Open Settings → Preferences and run a Manual Scan if you want "
                        "an on-demand refresh."
                    ),
                    (
                        "Click a card for more detail (Process Review, Storage) where "
                        "that card supports it."
                    ),
                    (
                        "Open Settings → Preferences to adjust refresh intervals, "
                        "visible cards, and appearance."
                    ),
                    (
                        "Optionally, open Settings → Nodes & Connections to discover "
                        "and pair another System Analyzer installation on your network."
                    ),
                    (
                        "Optionally, once you have paired peers, use All Systems to see "
                        "them together and set up cluster roles."
                    ),
                ),
            ),
            HelpSection(
                heading="You don't need another machine",
                paragraphs=(
                    (
                        "System Analyzer is fully useful on a single computer with "
                        "nothing paired. Discovery, pairing, and clusters are optional "
                        "features for people who run System Analyzer on more than one "
                        "machine -- they are never required to see your own system's "
                        "information."
                    ),
                ),
            ),
        ),
    ),
    HelpTopic(
        key="installing",
        title="Installing System Analyzer",
        summary="The real, current install commands for Windows, macOS, and Linux.",
        sections=(
            HelpSection(
                heading="Requirements",
                paragraphs=(
                    (
                        "System Analyzer needs Python 3.10 or newer. The installers "
                        "look for a suitable Python automatically."
                    ),
                ),
            ),
            HelpSection(
                heading="Windows",
                paragraphs=(
                    (
                        "Run the per-user installer script from a PowerShell prompt "
                        "in the project folder:"
                    ),
                ),
                bullets=(
                    "./install/install-user.ps1",
                    (
                        "Or, without cloning the repository first: "
                        "irm https://raw.githubusercontent.com/20204166/exp/main/"
                        "install/install-online.ps1 | iex"
                    ),
                    (
                        "The installer prints the folder it installed into (typically "
                        "your Python Scripts folder) and adds it to PATH if needed."
                    ),
                    "Launch the app afterward with: system-analyzer",
                    "Verify the install with: system-analyzer-snapshot --help",
                ),
            ),
            HelpSection(
                heading="macOS",
                paragraphs=("Run the same per-user installer used on Linux:",),
                bullets=(
                    "./install/install-user.sh",
                    (
                        "macOS ships Python 3.9 by default, which is too old. If the "
                        "installer reports this, install a newer Python first (for "
                        "example: brew install python@3.12) and re-run the installer, "
                        "or point it at that Python directly with "
                        "SA_SYSTEM_PYTHON=/path/to/python3.12 ./install/install-user.sh."
                    ),
                    "Launch the app afterward with: system-analyzer",
                ),
            ),
            HelpSection(
                heading="Linux",
                paragraphs=("Run the per-user installer:",),
                bullets=(
                    "./install/install-user.sh",
                    (
                        "Or, without cloning the repository first: "
                        "curl -fsSL https://raw.githubusercontent.com/20204166/exp/"
                        "main/install/install-online.sh | bash"
                    ),
                    (
                        "Tkinter must be available (the python3-tk system package on "
                        "most distributions)."
                    ),
                    "Optional: ./install-desktop.sh adds a desktop launcher entry.",
                    "Launch the app afterward with: system-analyzer",
                ),
            ),
            HelpSection(
                heading="Updating, rolling back, or removing",
                bullets=(
                    (
                        "Reinstall the current version: ./install/upgrade.sh (or "
                        "upgrade.ps1 on Windows)"
                    ),
                    (
                        "Roll back to a specific earlier version: "
                        "./install/rollback.sh <version>"
                    ),
                    "Remove the installed package: ./install/uninstall.sh",
                ),
            ),
        ),
    ),
    HelpTopic(
        key="dashboard",
        title="Dashboard & System Information",
        summary="What each of the six resource cards shows and means.",
        sections=(
            HelpSection(
                heading="CPU",
                paragraphs=(
                    (
                        "Shows current processor usage as a percentage, plus physical "
                        "and logical core counts, current/maximum frequency, and a "
                        "temperature reading where one is available. Click the card "
                        "to open Process Review sorted by CPU usage."
                    ),
                ),
            ),
            HelpSection(
                heading="Memory",
                paragraphs=(
                    (
                        "Shows memory used as a percentage and how much is available, "
                        "plus total/available/in-use RAM and swap usage. Click the "
                        "card to open Process Review sorted by memory usage."
                    ),
                ),
            ),
            HelpSection(
                heading="Storage",
                paragraphs=(
                    (
                        "Shows disk usage as a percentage and free space, plus your "
                        "Downloads folder location, current Trash size, and a drive "
                        "temperature reading when available. Click the card to open "
                        "the Storage review dialog."
                    ),
                ),
            ),
            HelpSection(
                heading="GPU",
                paragraphs=(
                    (
                        "Shows a concise graphics hardware name when it can be read. "
                        "GPU information genuinely varies by hardware, driver, and "
                        'operating system -- "Information unavailable" usually means '
                        "your GPU or platform doesn't expose the details this card "
                        "reads, not that something is broken."
                    ),
                ),
            ),
            HelpSection(
                heading="Network",
                paragraphs=(
                    (
                        "Shows current download/upload rates, total bytes since "
                        "startup, the active network interface, and whether a VPN "
                        "is detected."
                    ),
                ),
            ),
            HelpSection(
                heading="Battery",
                paragraphs=(
                    (
                        "Shows charge percentage, charging state, and time remaining "
                        'when a battery is present. "No battery" on a desktop is '
                        "expected, not an error -- it means the hardware has none, "
                        "which is different from a reading that failed."
                    ),
                ),
            ),
        ),
    ),
    HelpTopic(
        key="thermals",
        title="Thermals",
        summary="How the temperature graph and its states work.",
        sections=(
            HelpSection(
                heading="The graph",
                paragraphs=(
                    (
                        "The Thermals page plots recent temperature history for CPU "
                        "and, where available, GPU, storage, and battery. Dashed "
                        "lines mark warning and critical thresholds when they apply."
                    ),
                ),
            ),
            HelpSection(
                heading="What each state means",
                bullets=(
                    (
                        "Waiting for the first sample -- no reading has arrived yet; "
                        "this is normal for the first few seconds after opening the "
                        "page."
                    ),
                    (
                        "Temperature not supported -- this component genuinely has "
                        "no readable sensor on this machine."
                    ),
                    (
                        "Temperature temporarily unavailable (or a specific reason) "
                        "-- a reading was attempted and failed; this can resolve on "
                        "its own, or point to something you can fix (see "
                        "Troubleshooting)."
                    ),
                    "A plotted line -- valid, current readings.",
                ),
            ),
            HelpSection(
                heading="Why some sensors are missing",
                paragraphs=(
                    (
                        "Not every machine exposes every temperature. Desktop CPUs "
                        "commonly do; GPU, storage, and battery temperature depend "
                        "heavily on hardware and operating system, and a missing "
                        "reading there is expected on many machines rather than a "
                        "sign of a problem."
                    ),
                ),
            ),
        ),
    ),
    HelpTopic(
        key="processes",
        title="Process Review",
        summary="How reviewing and quitting processes works, safely.",
        sections=(
            HelpSection(
                heading="Reviewing processes",
                paragraphs=(
                    (
                        "Process Review lists running processes so you can request "
                        "that one quit. You select a process and ask it to quit "
                        "normally first -- System Analyzer never force-quits as a "
                        "first step."
                    ),
                ),
            ),
            HelpSection(
                heading="Protected vs. Can quit",
                paragraphs=(
                    (
                        "Each process is marked Protected or Can quit. Protected "
                        "processes cannot be selected at all -- this includes "
                        "operating-system-critical processes (things like your "
                        "shell, window manager, or system services) and processes "
                        "belonging to a different user account. This protection is "
                        "not configurable, by design."
                    ),
                ),
            ),
            HelpSection(
                heading="If a normal quit doesn't work",
                paragraphs=(
                    (
                        "Only if a requested quit doesn't succeed does System "
                        "Analyzer offer a second, separate confirmation to force it, "
                        "with an explicit warning that unsaved work may be lost. "
                        "Force quit is never the default action."
                    ),
                ),
            ),
        ),
    ),
    HelpTopic(
        key="storage",
        title="Storage & Safe Cleanup",
        summary="How Downloads review and cleanup work, and why nothing is deleted permanently.",
        sections=(
            HelpSection(
                heading="Reviewing your Downloads folder",
                paragraphs=(
                    (
                        "The Storage dialog can surface large files and verified "
                        "duplicates in your Downloads folder for you to review."
                    ),
                ),
            ),
            HelpSection(
                heading="Nothing is deleted permanently",
                bullets=(
                    ("You choose what to act on -- nothing is removed automatically."),
                    (
                        "Every removal goes to your operating system's Trash/Recycle "
                        "Bin, never a permanent delete."
                    ),
                    (
                        "You confirm before anything moves, and the confirmation "
                        "says exactly that: files are not permanently deleted."
                    ),
                ),
            ),
        ),
    ),
    HelpTopic(
        key="nodes",
        title="Nodes & Connections",
        summary="An overview of how System Analyzer machines relate to each other.",
        sections=(
            HelpSection(
                heading="Five separate ideas",
                paragraphs=(
                    (
                        "Nodes & Connections covers several distinct concepts that "
                        "are easy to blur together. Each one has its own Help topic:"
                    ),
                ),
                bullets=(
                    "Discovery -- seeing that another installation exists nearby.",
                    (
                        "Pairing & Trust -- deliberately establishing a trusted "
                        "relationship with a specific machine."
                    ),
                    (
                        "Remove Connection & Revoke -- the two different ways to "
                        "back out of a relationship, and how they differ."
                    ),
                    "Clusters -- optionally grouping already-trusted peers.",
                    "Coordinator & Workers -- optional roles inside a cluster.",
                ),
            ),
            HelpSection(
                heading="None of this is required",
                paragraphs=(
                    (
                        "You can ignore Nodes & Connections entirely and use System "
                        "Analyzer as a single-machine tool. Nothing here activates "
                        "on its own."
                    ),
                ),
            ),
        ),
    ),
    HelpTopic(
        key="discovery",
        title="Discovery",
        summary="Seeing other System Analyzer installations nearby -- and nothing more.",
        sections=(
            HelpSection(
                heading="What discovery does",
                paragraphs=(
                    (
                        "Discovery lets System Analyzer installations on the same "
                        "reachable local network see each other's presence -- "
                        "hostname, whether the version is compatible, and whether "
                        "it looks reachable."
                    ),
                ),
            ),
            HelpSection(
                heading="What discovery does NOT do",
                bullets=(
                    "It does not trust the other machine.",
                    "It does not grant any permission.",
                    "It does not join anything to a cluster.",
                    "It does not allow any remote action.",
                ),
                paragraphs=(
                    (
                        "A discovered machine is purely something you can now choose "
                        "to pair with -- discovery itself changes nothing."
                    ),
                ),
            ),
            HelpSection(
                heading="Network limitations",
                paragraphs=(
                    (
                        "Discovery needs a reachable local network path with "
                        "multicast/mDNS support. It will not find a machine across "
                        "a VPN that isolates multicast traffic, across separate "
                        "network segments, or when a firewall blocks the discovery "
                        "traffic. Turning discovery off in Preferences also stops "
                        "your own machine from being seen."
                    ),
                ),
            ),
        ),
    ),
    HelpTopic(
        key="pairing-trust",
        title="Pairing & Trust",
        summary="How a trusted relationship with another machine is actually established.",
        sections=(
            HelpSection(
                heading="The pairing flow",
                bullets=(
                    "You discover a peer.",
                    (
                        "You press Pair, and confirm the identity fingerprint shown "
                        "to you (this is you verifying you're pairing the machine "
                        "you actually mean to, over a channel you trust)."
                    ),
                    (
                        "The other machine's user sees an incoming pairing prompt "
                        "and chooses Accept or Reject."
                    ),
                    "Only after Accept does a trusted peer relationship exist.",
                ),
            ),
            HelpSection(
                heading="Three different things",
                paragraphs=(
                    (
                        "Discovered, Paired/Trusted, and Authorized are three "
                        "different states, not synonyms:"
                    ),
                ),
                bullets=(
                    'Discovered means only "visible on the network."',
                    (
                        "Paired/Trusted means both sides deliberately agreed to the "
                        "relationship."
                    ),
                    (
                        "Authorized is about what a trusted peer is allowed to do "
                        "(see Permissions & Remote Access) -- trust alone does not "
                        "hand over every permission."
                    ),
                ),
            ),
            HelpSection(
                heading="Why the fingerprint matters",
                paragraphs=(
                    (
                        "The fingerprint shown during pairing helps you confirm the "
                        "machine you're about to trust is really the one you "
                        "expect, rather than one that merely claims the same name."
                    ),
                ),
            ),
        ),
    ),
    HelpTopic(
        key="connections",
        title="Remove Connection & Revoke",
        summary="Two different actions with two different effects -- don't confuse them.",
        sections=(
            HelpSection(
                heading="Remove Connection",
                paragraphs=(
                    (
                        "Disconnects the active session with a peer. The underlying "
                        "trusted pairing is preserved -- you can reconnect without "
                        "pairing again."
                    ),
                ),
            ),
            HelpSection(
                heading="Revoke",
                paragraphs=(
                    (
                        "Invalidates the trust relationship itself. A new pairing "
                        "invite is required before that machine is trusted again. "
                        "Revoking does not hide the machine from Discovery forever "
                        "-- if it's still advertising itself on the network, it "
                        "will simply reappear as an untrusted, discovered peer, "
                        "exactly like any machine you've never paired."
                    ),
                ),
            ),
            HelpSection(
                heading="Manual hosts",
                paragraphs=(
                    (
                        "A manually-added host (one you typed in rather than "
                        "discovered) works the same way: removing it deletes its "
                        "saved connection details and revokes its trust, so you'll "
                        "need to add and pair it again to reconnect."
                    ),
                ),
            ),
        ),
    ),
    HelpTopic(
        key="clusters",
        title="Clusters",
        summary="Grouping already-trusted peers -- without pooling their hardware.",
        sections=(
            HelpSection(
                heading="What a cluster is",
                paragraphs=(
                    (
                        "A cluster groups machines you've already paired so you can "
                        "see and coordinate them together, in the All Systems page. "
                        "Every machine in a cluster remains its own independent "
                        "computer."
                    ),
                ),
            ),
            HelpSection(
                heading="What a cluster is NOT",
                bullets=(
                    "Not pooled RAM.",
                    "Not pooled CPU.",
                    "Not a shared operating system.",
                    "Not distributed memory.",
                ),
                paragraphs=(
                    (
                        "Each machine still runs its own copy of System Analyzer "
                        "and only reports on itself."
                    ),
                ),
            ),
            HelpSection(
                heading="Clusters build on pairing, not the other way around",
                paragraphs=(
                    (
                        "A machine has to already be a trusted, paired peer before "
                        "it can take part in a cluster. Joining a cluster never "
                        "substitutes for pairing."
                    ),
                ),
            ),
        ),
    ),
    HelpTopic(
        key="coordinator-worker",
        title="Coordinator & Workers",
        summary="Optional roles inside a cluster -- layered on trust, not a replacement for it.",
        sections=(
            HelpSection(
                heading="Coordinator is a role, not a trust authority",
                paragraphs=(
                    (
                        "One machine in a cluster can act as coordinator. Being "
                        "coordinator lets that machine assign roles and eligible "
                        "work to other already-paired peers in the cluster. It does "
                        "not grant automatic trust over anyone, and it cannot pair "
                        "a machine on its own -- pairing always still requires the "
                        "explicit accept/reject flow described in Pairing & Trust."
                    ),
                ),
            ),
            HelpSection(
                heading="Worker",
                paragraphs=(
                    (
                        "A worker is a paired peer eligible to take on certain "
                        "cluster work assigned by the coordinator. A worker still "
                        'only reads and acts on itself -- "pooled PC" is not an '
                        "accurate way to think about this."
                    ),
                ),
            ),
            HelpSection(
                heading="What stays fixed",
                bullets=(
                    (
                        "Reading a specific machine's own information always "
                        "happens on that machine -- a coordinator can request it, "
                        "but cannot relocate that read elsewhere."
                    ),
                    (
                        "Only some kinds of work can be reassigned between "
                        "eligible workers at all -- most information is inherently "
                        "tied to the machine it describes."
                    ),
                    (
                        "Changing a peer's role (worker/coordinator) does not "
                        "silently change its trust or pairing status."
                    ),
                ),
            ),
        ),
    ),
    HelpTopic(
        key="permissions",
        title="Permissions & Remote Access",
        summary="Trust and permission are different things.",
        sections=(
            HelpSection(
                heading="What trust grants by default",
                paragraphs=(
                    (
                        "A newly-paired peer is read-only by default: it can view "
                        "your dashboard and component details, review your process "
                        "list, and review storage -- and nothing more. You'll see "
                        'this reflected as "Remote read-only" in the app.'
                    ),
                ),
            ),
            HelpSection(
                heading="Granting more",
                paragraphs=(
                    (
                        "From Nodes & Connections you can explicitly grant a "
                        "trusted peer additional permissions -- reviewing "
                        "processes, terminating processes, or force-terminating "
                        "them -- one at a time, per peer. None of these are "
                        "granted automatically just because a peer is trusted."
                    ),
                ),
            ),
            HelpSection(
                heading="Remote read-only in practice",
                paragraphs=(
                    (
                        "When a connection is read-only, actions that would change "
                        "something on the remote machine are blocked with a clear "
                        "message rather than silently failing -- you can look, but "
                        "not act, until that specific permission is granted."
                    ),
                ),
            ),
        ),
    ),
    HelpTopic(
        key="settings",
        title="Settings & Appearance",
        summary="What you can actually configure today.",
        sections=(
            HelpSection(
                heading="Preferences",
                bullets=(
                    (
                        "Refresh intervals -- how often each card (CPU, memory, "
                        "network, GPU, storage, battery) re-reads its sensor."
                    ),
                    "Dashboard Cards -- show or hide individual cards.",
                    (
                        "Manual Scan -- trigger an on-demand scan, or cancel one in "
                        "progress."
                    ),
                    (
                        "Hide unavailable cards automatically -- hides a card only "
                        "once its hardware is proven absent (like no battery); a "
                        "one-off failed read never hides a card by itself."
                    ),
                    (
                        "Accent theme -- changes the accent colour used across "
                        "buttons, progress bars, and dashboard cards."
                    ),
                    "Reset Preferences to Defaults.",
                ),
            ),
            HelpSection(
                heading="Per-peer personalization",
                paragraphs=(
                    (
                        "In Nodes & Connections, each trusted peer can be given its "
                        "own display colour, which helps tell machines apart at a "
                        "glance once you have more than one paired."
                    ),
                ),
            ),
        ),
    ),
    HelpTopic(
        key="platform-support",
        title="Platform Support",
        summary="Honest, practical differences between Windows, macOS, and Linux.",
        sections=(
            HelpSection(
                heading="What varies by platform",
                bullets=(
                    (
                        "Temperature sensors -- CPU temperature is commonly "
                        "available; GPU, storage, and battery temperature depend "
                        "on hardware and OS, and some Windows machines need a "
                        "third-party sensor tool or administrator privileges (see "
                        "Troubleshooting)."
                    ),
                    ("GPU details -- vary by hardware and driver on every platform."),
                    (
                        "Battery -- naturally unavailable on desktop hardware; "
                        "that's expected, not a defect."
                    ),
                    (
                        "Some platform integrations are optional and degrade "
                        "gracefully when unavailable rather than causing a crash."
                    ),
                ),
            ),
            HelpSection(
                heading="Where to look for detail",
                paragraphs=(
                    (
                        "This page summarizes practical differences you'll "
                        "actually notice. It intentionally does not reproduce the "
                        "project's full internal compatibility matrix, which is "
                        "developer-facing."
                    ),
                ),
            ),
        ),
    ),
    HelpTopic(
        key="troubleshooting",
        title="Troubleshooting",
        summary="Real, current failure modes -- symptom, likely reason, safe next step.",
        sections=(
            HelpSection(
                heading="Peer not discovered",
                paragraphs=(
                    (
                        "Symptom: another installation never appears in Nodes & "
                        "Connections. Likely reason: it's not on the same reachable "
                        "local network segment, a VPN is isolating multicast "
                        "traffic, discovery is turned off on one side, or a "
                        "firewall is blocking discovery traffic. Safe step: confirm "
                        "both machines are on the same LAN and that Discovery is "
                        "enabled in Preferences on both; check firewall rules for "
                        "the app specifically rather than disabling your firewall "
                        "entirely."
                    ),
                ),
            ),
            HelpSection(
                heading="Pair request not appearing",
                paragraphs=(
                    (
                        "Symptom: you pressed Pair, but the other user never sees a "
                        "prompt. Likely reason: the peer went offline mid-request, "
                        "or a firewall is blocking the connection. Safe step: "
                        "confirm the peer is still online and reachable, then try "
                        "pairing again."
                    ),
                ),
            ),
            HelpSection(
                heading="Unable to connect to a trusted peer",
                paragraphs=(
                    (
                        "Symptom: a previously-paired peer shows as unreachable. "
                        "Likely reason: it's offline, its address changed, or its "
                        "trust was revoked from the other side (which would require "
                        "a fresh pairing). Safe step: check the peer is online; if "
                        "trust was revoked, pair again."
                    ),
                ),
            ),
            HelpSection(
                heading="Fingerprint mismatch",
                paragraphs=(
                    (
                        "Symptom: the identity fingerprint changes for a peer you "
                        "already trust. Likely reason: the peer reinstalled System "
                        "Analyzer or its identity changed for a legitimate reason "
                        "-- but this is also what you'd see if a different machine "
                        "were impersonating it. Safe step: reconfirm the fingerprint "
                        "through a channel you trust (in person, a known chat) "
                        "before accepting it again."
                    ),
                ),
            ),
            HelpSection(
                heading='Thermal graph stuck on "Waiting for the first sample"',
                paragraphs=(
                    (
                        "This is normal for the first few seconds. If it persists, "
                        "see the Thermals topic for what each state (Waiting for "
                        "the first sample / Temperature not supported / "
                        "Temperature temporarily unavailable) actually means -- "
                        "they are not the same problem."
                    ),
                ),
            ),
            HelpSection(
                heading="Windows: CPU temperature never shows",
                paragraphs=(
                    (
                        "Symptom: the Thermals page says temperature requires "
                        "administrator privileges. Likely reason: your machine's "
                        "ACPI thermal sensor genuinely requires elevated access on "
                        "Windows, which System Analyzer does not request by "
                        "default. Safe step: either run System Analyzer as "
                        "Administrator, or install and run a WMI-sharing sensor "
                        "tool such as LibreHardwareMonitor, which can supply the "
                        "same reading without elevating System Analyzer itself."
                    ),
                ),
            ),
            HelpSection(
                heading="GPU information unavailable",
                paragraphs=(
                    (
                        "Symptom: the GPU card says information is unavailable. "
                        "Likely reason: your GPU or driver doesn't expose the "
                        "details this card reads on your platform. Safe step: none "
                        "needed -- this reflects a genuine hardware/driver "
                        "limitation, not an app failure."
                    ),
                ),
            ),
            HelpSection(
                heading="No battery detected",
                paragraphs=(
                    (
                        "Symptom: the Battery card says no battery. Likely reason: "
                        "you're on desktop hardware, which has none. Safe step: "
                        "none needed -- this is the expected state, distinct from "
                        "a battery reading that fails."
                    ),
                ),
            ),
            HelpSection(
                heading="Manual Scan failure",
                paragraphs=(
                    (
                        "Symptom: a manual scan reports a failure for one card. "
                        "Likely reason: a transient sensor read error. Safe step: "
                        "try the scan again; if one card consistently fails while "
                        "others succeed, that card's underlying sensor is the "
                        "specific thing to investigate."
                    ),
                ),
            ),
        ),
    ),
    HelpTopic(
        key="about",
        title="About System Analyzer",
        summary="What this application is, in plain terms.",
        sections=(
            HelpSection(
                heading="What it is",
                paragraphs=(
                    (
                        "System Analyzer is a desktop diagnostics and "
                        "safe-maintenance utility. It shows system resource "
                        "information, thermal history, process information, and "
                        "storage-review candidates, and can optionally communicate "
                        "with trusted System Analyzer peers on your network."
                    ),
                ),
            ),
            HelpSection(
                heading="What it deliberately does not do",
                bullets=(
                    "No arbitrary remote shell or remote command execution.",
                    "No automatic destructive cleanup -- you always choose.",
                    "No permanent file deletion -- removals go to Trash.",
                    "No pooled RAM/CPU across machines.",
                    "No fan control or overclocking.",
                ),
            ),
            HelpSection(
                heading="Principles",
                bullets=(
                    (
                        "Useful information, presented honestly -- including when "
                        "something is unavailable."
                    ),
                    "Safe, user-controlled maintenance, never automatic.",
                    (
                        "Fail-soft hardware support -- a missing sensor degrades "
                        "gracefully instead of breaking the app."
                    ),
                    (
                        "Explicit trust between machines -- nothing is trusted "
                        "just because it was seen on the network."
                    ),
                ),
            ),
        ),
    ),
)


def find_topic(key: str) -> HelpTopic | None:
    """Return the topic with the given key, or ``None`` if it doesn't exist."""

    return next((topic for topic in HELP_TOPICS if topic.key == key), None)
