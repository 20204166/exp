# Windows Testing Protocol — `exp` / `system-analyzer`

Status: physical Windows testing is the **only** next step. No more speculative
code audits, no production-code changes, until a real Windows-wheel failure
has been reproduced on hardware.

## Machine role

This Windows machine (`C:\Users\BTN17`) is a **black-box runtime machine
only**. It installs and runs the published wheel and nothing else.

Never, on Windows:
- clone the repository
- edit source
- run `pytest` / `Ruff` / `Pyright`
- set up a Windows coding/dev environment

Install/update the wheel here with:

```powershell
irm https://raw.githubusercontent.com/20204166/exp/main/install/install-online.ps1 | iex
```

Last run on this machine (2026-09-17): upgraded `system-analyzer` 1.6.0.3 →
1.6.0.5 (deps: psutil, send2trash, nvidia-ml-py, zeroconf, cryptography, cffi,
pycparser, ifaddr). Console entry point: `system-analyzer`, installed to
`C:\Users\BTN17\AppData\Roaming\Python\Python312\Scripts`.

## Per-failure loop

**WINDOWS**
1. Reproduce the failure using the *installed wheel* (never source).
2. Collect exact evidence: UI behavior observed + PowerShell/runtime output
   (commands run, full error text, exit codes).

**LINUX** (separate dev environment)
1. Identify the first broken boundary from the Windows evidence.
2. Add the strongest Linux-runnable regression test for it.
3. Implement the smallest portable fix.
4. Verify both the native Linux path and the emulated-Windows branch.
5. Build a new wheel.

**WINDOWS**
1. Install the new wheel (rerun the installer above).
2. Rerun the exact failed scenario and confirm the fix against the same
   evidence collected in step 1.

## Explicit non-goals

Do **not** preemptively fix any of the following unless a physical Windows
run actually reproduces it:
- `candidate.addresses[0]`
- firewall behavior
- IPv6 handling
- VPN handling
- any other currently hypothetical Windows problem

## Constraints on fixes

- Preserve existing Linux behavior.
- Keep fixes portable / macOS-compatible whenever possible.
- Fix only the first broken boundary actually observed — no speculative
  hardening beyond the reproduced failure.
