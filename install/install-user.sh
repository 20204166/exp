#!/usr/bin/env bash
# Install System Analyzer into the CURRENT USER's Python WITHOUT a virtual
# environment, so `system-analyzer` runs directly from any directory.
#
# You do NOT need to be inside the repo to run this: give the full path, e.g.
#   /path/to/exp/install/install-user.sh
# It locates the repo (and the committed wheel in dist/) from its own location.
#
#   install-user.sh              # per-user install  -> ~/.local/bin
#   install-user.sh --system     # machine-wide      -> /usr/local/bin (uses sudo)
#   install-user.sh 1.2.2.0      # install a specific wheel from dist/
#
#   - uses the system interpreter (SA_SYSTEM_PYTHON to override; default
#     /usr/bin/python3 then python3)
#   - installs the built wheel from dist/ together with its dependencies
#   - automatically adds --break-system-packages on PEP 668 systems
#   - after install, run `system-analyzer` from anywhere (it is on PATH)
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$here/install/_common.sh"

mode="user"
version=""
for arg in "$@"; do
  case "$arg" in
    --system) mode="system" ;;
    *) version="$arg" ;;
  esac
done

if [ -n "${SA_SYSTEM_PYTHON:-}" ]; then py="$SA_SYSTEM_PYTHON"
elif [ -x /usr/bin/python3 ]; then py=/usr/bin/python3
else py=python3; fi

wheel="$(wheel_path "$version")"
[ -n "$wheel" ] && [ -f "$wheel" ] || { echo "no wheel found; run install/build.sh first" >&2; exit 1; }

echo "System interpreter: $py ($("$py" --version 2>&1))"
echo "Verifying wheel: $(basename "$wheel")"
(cd "$here" && "$py" -m maintenance._release verify-wheel "$wheel")

extra=()
if "$py" - <<'PY'
import pathlib
import sysconfig
import sys

# The PEP 668 marker lives beside the stdlib (e.g.
# /usr/lib/python3.12/EXTERNALLY-MANAGED), not under sys.prefix.
candidates = (sysconfig.get_path("stdlib"), sys.prefix)
for base in candidates:
    if (pathlib.Path(base) / "EXTERNALLY-MANAGED").exists():
        raise SystemExit(0)
raise SystemExit(1)
PY
then
  echo "PEP 668 externally-managed detected; using --break-system-packages"
  extra=(--break-system-packages)
fi

if [ "$mode" = "system" ]; then
  command -v sudo >/dev/null 2>&1 || { echo "sudo is required for --system" >&2; exit 1; }
  echo "Installing machine-wide (system Python, no venv)..."
  sudo "$py" -m pip install "${extra[@]}" "$wheel"
  echo "Installed. Console scripts are in: /usr/local/bin"
  echo "Run: system-analyzer"
else
  echo "Installing into the user environment (no venv)..."
  "$py" -m pip install --user "${extra[@]}" "$wheel"
  bin_dir="$("$py" -c 'import sysconfig;print(sysconfig.get_path("scripts", scheme="posix_user"))' 2>/dev/null || echo "$HOME/.local/bin")"
  echo "Installed. Console scripts are in: $bin_dir"
  if echo "$PATH" | tr ':' '\n' | grep -qx "$bin_dir"; then
    echo "That directory is already on PATH: run 'system-analyzer'"
  else
    echo "Add it to PATH once, e.g.:"
    echo "  echo 'export PATH=\"$bin_dir:\$PATH\"' >> ~/.bashrc"
    echo "  export PATH=\"$bin_dir:\$PATH\""
  fi
fi
echo "Verify: system-analyzer-snapshot --help"