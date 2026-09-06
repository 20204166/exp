#!/usr/bin/env bash
# Shared helpers for the System Analyzer install/release scripts (Unix-like:
# Linux, macOS, and WSL). Windows users use the equivalent *.ps1 scripts.
# Safety: no sudo by default; explicit venv target (repo .venv by default,
# override SA_PYTHON); no network for the committed-wheel path; clear version
# display.
set -euo pipefail

# The repo root IS the package root (single project layout).
pkg_dir() { cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd; }

# Ordered candidate interpreters: named 3.10+ first (python.org/Homebrew
# installs commonly register python3.10..python3.13), then Homebrew and
# python.org framework locations even when not on PATH, then the system
# /usr/bin/python3, then bare python3/python.
python_candidates() {
  local list=() name
  for name in python3.13 python3.12 python3.11 python3.10; do
    if command -v "$name" >/dev/null 2>&1; then list+=("$name"); fi
  done
  for path in /opt/homebrew/bin/python3.13 /opt/homebrew/bin/python3.12 \
              /opt/homebrew/bin/python3.11 /opt/homebrew/bin/python3.10 \
              /usr/local/bin/python3.13 /usr/local/bin/python3.12 \
              /usr/local/bin/python3.11 /usr/local/bin/python3.10; do
    [ -x "$path" ] && list+=("$path")
  done
  [ -x /usr/bin/python3 ] && list+=(/usr/bin/python3)
  list+=(python3 python)
  printf '%s\n' "${list[@]}"
}

# Return the first candidate that is Python 3.10+ (probed quietly).
first_python_ge_310() {
  local candidate
  while IFS= read -r candidate; do
    if require_python "$candidate" >/dev/null 2>&1; then
      echo "$candidate"
      return 0
    fi
  done < <(python_candidates)
  return 1
}

resolve_python() {
  if [ -n "${SA_PYTHON:-}" ]; then echo "$SA_PYTHON"; return; fi
  local r found; r="$(pkg_dir)"
  if [ -x "$r/.venv/Scripts/python.exe" ]; then echo "$r/.venv/Scripts/python.exe"; return; fi
  if [ -x "$r/.venv/bin/python" ]; then echo "$r/.venv/bin/python"; return; fi
  if found="$(first_python_ge_310)"; then echo "$found"; return; fi
  echo "python"
}

wheel_path() {
  local version="${1:-}" dist; dist="$(pkg_dir)/dist"
  if [ -n "$version" ]; then
    local w="$dist/system_analyzer-$version-py3-none-any.whl"
    [ -f "$w" ] || { echo "wheel not found for $version: $w" >&2; exit 1; }
    echo "$w"; return
  fi
  ls -t "$dist"/system_analyzer-*.whl 2>/dev/null | head -1
}

show_version() { "$1" -m pip show system-analyzer 2>/dev/null | grep '^Version:' || true; }

# System Analyzer uses PEP 604 union types (e.g. `threading.Event | None`) so
# it requires Python 3.10+. Fail fast with a clear message instead of a
# confusing import-time TypeError on older interpreters (e.g. the macOS 3.9
# system Python).
require_python() {
  local py="$1" v major minor
  v="$("$py" -c 'import sys; print("%d.%d" % sys.version_info[:2])')" || return 1
  major="${v%%.*}"; minor="${v#*.}"; minor="${minor%%.*}"
  if [ "$major" -lt 3 ] || { [ "$major" -eq 3 ] && [ "$minor" -lt 10 ]; }; then
    echo "System Analyzer requires Python 3.10 or newer; this interpreter is" \
         "$v ($py)." >&2
    echo "Install a newer Python (e.g. 'brew install python@3.12' on macOS) or" \
         "use a 3.10+ virtual environment, then retry." >&2
    return 1
  fi
  return 0
}

# Return 0 when the interpreter has the declared setuptools build backend
# (>= 68). Used by build.sh to decide between the offline no-isolation path
# and pip build isolation, and to fail fast with a clear message instead of a
# pip traceback when the backend is genuinely missing.
require_build_backend() {
  local py="$1"
  "$py" -c 'import re, setuptools
m = re.match(r"^(\d+)\.(\d+)", setuptools.__version__)
raise SystemExit(0 if m and (int(m.group(1)), int(m.group(2))) >= (68, 0) else 1)'
}