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

```sh
pip install .
```

Installs the app into the active environment (no PyPI publishing; everything
stays local). The following commands become available on `PATH`:

| Command                    | Purpose                                        |
| -------------------------- | ---------------------------------------------- |
| `system-analyzer`          | Launch the desktop GUI                          |
| `system-analyzer-snapshot` | Print a read-only system snapshot as JSON      |

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