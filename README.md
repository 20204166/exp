# System Analyzer

A local desktop dashboard and safe-cleanup tool for the current machine. It
scans system components (CPU, memory, storage, GPU, network, battery), reports
health warnings, and offers careful cleanup actions for user processes and
Downloads files. Nothing is published or uploaded anywhere; the project is
installed and run locally.

## Layout

```
main.py                  entrypoint (python main.py / system-analyzer)
algo.py, window.py       app facade and Tk controller (kept top-level for
                         compatibility with historical imports)
maintenance/             shared implementation package
maintenance/components/  component subsystem (scan primitives, process safety,
                         downloads, GPU, background, catalog, coordinator,
                         clock/governor)
maintenance/ui/          presentation layer (styles, layout, pages, status)
maintenance/snapshot.py  read-only snapshot CLI (system-analyzer-snapshot)
pyproject.toml           local packaging configuration
```

## Dependencies

- `psutil>=5.9` — required for most scans and process inspection.
- `send2trash>=1.8` — required for the Storage cleanup action (move to Trash).
- `nvidia-ml-py>=12.0` — optional NVIDIA GPU detail on non-Darwin platforms
  (`pip install -e .` installs it by default; the app runs without it, showing
  "GPU information unavailable").
- `zeroconf>=0.131` — local-network mDNS discovery of other running System
  Analyzer instances. Discovery is presence-only; authenticated trusted nodes
  can provide the verified remote read paths and target-side guarded process
  actions. Remote file cleanup remains read-only.

The GUI additionally requires a Python build with `tkinter` available.

## Development install

```sh
python -m venv .venv
. .venv/bin/activate
pip install -e .
```

After this, `python main.py` and the `system-analyzer` command both launch the
GUI. Running `python main.py` directly from the source tree keeps working
without any install step (development usage is preserved).

## Normal local install

The distribution builds a wheel into `dist/` (with `dist/SHA256SUMS`) and
installs it non-editable, so `system-analyzer` runs from anywhere without
needing the source folder or a virtual environment. The install tooling is
**universal**: `.sh` scripts work on Linux, macOS, and WSL; `.ps1` scripts
work on native Windows (and any OS with PowerShell).

| OS        | Per-user install            | Machine-wide         |
| --------- | --------------------------- | -------------------- |
| Linux     | `./install/install-user.sh` | `./install/install-user.sh --system` |
| macOS     | `./install/install-user.sh` | `./install/install-user.sh --system` |
| WSL       | `./install/install-user.sh` | `./install/install-user.sh --system` |
| Windows   | `./install/install-user.ps1` | `./install/install.ps1` (targets a venv) |

On Windows, the second column is a target-venv installer, not a machine-wide
system install.

All scripts auto-find a Python 3.10+, verify the committed wheel, install the
app with its dependencies, and print the exact PATH step for your shell/OS.
`build.ps1` / `verify.ps1` / `upgrade.ps1` / `rollback.ps1` / `uninstall.ps1`
mirror their `.sh` counterparts for the release workflow on Windows.

### Install without the repository folder

The online installers work from any directory and download the latest wheel
from GitHub. They do not require `cd` into the repository:

```sh
curl -fsSL https://raw.githubusercontent.com/20204166/exp/main/install/install-online.sh | bash
```

On Windows PowerShell:

```powershell
irm https://raw.githubusercontent.com/20204166/exp/main/install/install-online.ps1 | iex
```

After adding the printed scripts directory to PATH, `system-analyzer` works
from any folder. The repository-local scripts remain available for offline
wheel installs and release management.

If a shell still reports `command not found`, use the exact `Direct launcher`
path printed by the installer, run `hash -r`, or open a new terminal after
updating PATH.

### Requirements

- **Python 3.10 or newer** (the app uses modern type syntax). The install
  scripts automatically find a 3.10+ interpreter (`python3.10`…`python3.13`,
  Homebrew/python.org locations, then the system Python); if only an older
  one exists they print a clear message and stop. macOS ships Python 3.9 as
  `/usr/bin/python3` — use your installed newer Python (e.g. `brew install
  python@3.12`, then `python3.12 -m venv .venv`), or point the script at it:
  `SA_SYSTEM_PYTHON=/path/to/python3.12 ./install/install-user.sh`.
- **tkinter** — the only non-pip prerequisite (system package `python3-tk` on
  Linux; included with python.org/Homebrew builds on macOS).

### Common install commands

Use the command that matches your situation:

| Situation | Command |
| --------- | ------- |
| Linux/macOS/WSL, per-user install | `./install/install-user.sh` |
| Linux/macOS/WSL, machine-wide install | `./install/install-user.sh --system` |
| Linux/macOS/WSL, reinstall or clean-install | `./install/install-user.sh` |
| Linux/macOS/WSL, install a specific wheel from `dist/` | `./install/install-user.sh 1.2.2.0` |
| Linux/macOS/WSL, online install from anywhere | `curl -fsSL https://raw.githubusercontent.com/20204166/exp/main/install/install-online.sh | bash` |
| Linux/macOS/WSL, online reinstall of the same wheel version | `curl -fsSL https://raw.githubusercontent.com/20204166/exp/main/install/install-online.sh | bash -s -- --force-reinstall` |
| Windows, per-user install | `./install/install-user.ps1` |
| Windows, install into a specific venv | `./install/install.ps1 -Python C:\Path\To\Python312\python.exe` |
| Windows, reinstall the same wheel into that venv | `./install/upgrade.ps1 -Python C:\Path\To\Python312\python.exe` |

Notes:
- `install-user.sh` auto-finds a Python 3.10+, verifies the committed wheel,
  installs it together with its dependencies, and prints where the
  `system-analyzer` scripts landed (`~/.local/bin` by default).
- The installers always remove existing `system-analyzer` distributions,
  force-reinstall the selected wheel, and verify the installed version and
  imported module paths. This prevents a stale same-version or lower-version
  install from surviving the release.
- On Windows, `install.ps1` already uses `--force-reinstall` internally for the
  target venv; use `upgrade.ps1` when you want a built-and-reinstalled update
  in one step.

Install into the current user's Python (no virtual environment, deps pulled in
automatically, PEP 668 handled). Run it **from inside the repo**, or give the
**real absolute path** from anywhere:

```sh
./install/install-user.sh
# or, from anywhere:
/path/to/your/clone/install/install-user.sh   # use your actual clone path
```

That verifies the committed wheel, installs it together with all its
dependencies, and prints where the `system-analyzer` scripts landed
(`~/.local/bin` by default). Add that directory to `PATH` once, then run from
**any** directory:

```sh
system-analyzer          # launch the GUI
system-analyzer-snapshot # read-only JSON snapshot
```

Install a specific wheel version (kept in `dist/` for rollback):

```sh
./install/install-user.sh 1.2.2.0
```

Reinstall the current wheel contents even if the version is already present:

```sh
./install/install-user.sh --force-reinstall
./install/install-user.sh --system --force-reinstall
```

### Machine-wide install (system Python, no venv)

Same script with `--system` installs into the system Python (uses `sudo`,
scripts land in `/usr/local/bin`, no `PATH` change needed):

```sh
./install/install-user.sh --system
```

If you need to force the same wheel version onto the system Python, add
`--force-reinstall`.

Equivalent manual commands:

```sh
pip install --user --break-system-packages dist/system_analyzer-*.whl   # per-user
sudo pip install --break-system-packages dist/system_analyzer-*.whl     # machine-wide
```

On PEP 668 Linux systems (e.g. Ubuntu 24.04+, Debian 12+) pip refuses installs
unless `--break-system-packages` is given — the script adds it automatically.
After either install the app is independent of the repo folder (a real install,
not editable): you can delete the clone and `system-analyzer` keeps working.

### Troubleshooting

**`TypeError: unsupported operand type(s) for |: 'type' and 'NoneType'` (or the
script says "requires Python 3.10")** — the interpreter is older than 3.10
(macOS ships Python 3.9 as `/usr/bin/python3`). Use a 3.10+ Python:

```sh
# macOS: install a newer Python, then a venv from it
brew install python@3.12
python3.12 -m venv .venv
. .venv/bin/activate
pip install .
# or point the install script at your newer Python:
SA_SYSTEM_PYTHON=/path/to/python3.12 ./install/install-user.sh
```

**`externally-managed-environment`** — pip is blocking installs into
system/user Python (Ubuntu 24.04+ / Debian 12+). The fix is
`--break-system-packages`, which `install-user.sh` already applies:

```sh
./install/install-user.sh            # per-user (handles PEP 668)
./install/install-user.sh --system   # machine-wide (sudo)
```

Manual fallbacks:

```sh
pip install --user --break-system-packages dist/system_analyzer-*.whl
sudo pip install --break-system-packages dist/system_analyzer-*.whl
```

Or use a virtual environment, which sidesteps PEP 668 entirely:

```sh
python -m venv .venv
. .venv/bin/activate
pip install .
```

**`no such option: --break-system-packages`** — pip is older than 23.0. The
script detects this and retries without the flag (those pip versions predate
PEP 668 anyway); if you are typing the manual commands, upgrade pip or use a
venv.

**`pip install -e` says "option requires 1 argument"** — the `.` is required:
run `pip install -e .` (and be inside the repo).

### Dev/venv install

```sh
python -m venv .venv
. .venv/bin/activate
pip install -e .
```

The following commands become available on `PATH`:

| Command                    | Purpose                                        |
| -------------------------- | ---------------------------------------------- |
| `system-analyzer`          | Launch the desktop GUI                          |
| `system-analyzer-snapshot` | Print a read-only system snapshot as JSON      |

### Wheel build / release automation

```sh
./install/build.sh      # auto-bumps version, builds dist/system_analyzer-*.whl, writes dist/SHA256SUMS
./install/verify.sh     # verifies the newest wheel (content + checksums)
./install/upgrade.sh    # builds (if needed) and installs the latest wheel
./install/rollback.sh 1.0.0.0   # reinstall a previous wheel kept in dist/
./install/uninstall.sh  # remove the app
```

The package version is a single source of truth in `maintenance/_version.py`;
`build.sh` auto-bumps it (patch/feature/minor) only when the source inputs
differ from the newest wheel, so rebuilds are no-ops unless something changed.
The app needs only its declared dependencies plus a Python build with
`tkinter` (the only non-pip prerequisite).

## Run

```sh
system-analyzer
# or
python main.py
```

The read-only snapshot command reuses the same scanner implementation — no
code duplication:

```sh
system-analyzer-snapshot --help
system-analyzer-snapshot
system-analyzer-snapshot --compact
```

## Linux desktop launcher

An optional menu entry can be installed for the current user (it uses the
user's own `XDG_DATA_HOME`/`$HOME`, never a hard-coded path):

```sh
./install-desktop.sh
```

This copies `packaging/system-analyzer.desktop` into
`${XDG_DATA_HOME:-$HOME/.local/share}/applications`. The entry launches the
`system-analyzer` command from `PATH`. Remove it with:

```sh
rm -f "${XDG_DATA_HOME:-$HOME/.local/share}/applications/system-analyzer.desktop"
```

## Configuration and logs

- Preferences: per-user config file under `~/.config/system-analyzer` (Linux)
  or the platform equivalent (see `maintenance/preferences.py`).
- Logs: per-user rotating log under `~/.local/state/system-analyzer` (Linux),
  falling back to stderr when the state directory is unavailable.

## Tests

```sh
python -m unittest discover -s tests -v
```

For the declared Python 3.10 floor, install the test compatibility dependency
before running the suite:

```sh
python -m pip install -r requirements-dev.txt
```

GUI tests use fake masters/widgets (or a live Tk root only when a display is
available) so the suite runs headless. Static checks:

```sh
ruff check .
ruff format --check .
pyright
mypy --ignore-missing-imports .
```

## Further reading

- `maintenance/README.md` — subsystem and legacy/compatibility surface notes.
- `maintenance/components/README.md` — component subsystem module index.
