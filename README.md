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
                         downloads, GPU, background, catalog, coordinator)
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
needing the source folder or a virtual environment.

### One-command install — no venv, system/user Python

Install into the current user's Python (no virtual environment, deps pulled in
automatically, PEP 668 handled):

```sh
./install/install-user.sh
```

That verifies the committed wheel, installs it together with all its
dependencies, and prints where the `system-analyzer` scripts landed
(`~/.local/bin` by default). Add that directory to `PATH` once, then:

```sh
system-analyzer          # launch the GUI
system-analyzer-snapshot # read-only JSON snapshot
```

Equivalent manual command (after `./install/build.sh`):

```sh
pip install --user --break-system-packages dist/system_analyzer-*.whl
```

On PEP 668 Linux systems (e.g. Ubuntu 24.04+) pip refuses user installs unless
`--break-system-packages` is given — the script adds it automatically. For a
machine-wide install instead, use `sudo pip install --break-system-packages .`.

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