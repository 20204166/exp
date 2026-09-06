#!/usr/bin/env bash
# Shared helpers for the System Analyzer install/release scripts (Linux).
# Safety: no sudo; explicit venv target (repo .venv by default, override
# SA_PYTHON); no network for the committed-wheel path; clear version display.
set -euo pipefail

# The repo root IS the package root (single project layout).
pkg_dir() { cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd; }

resolve_python() {
  if [ -n "${SA_PYTHON:-}" ]; then echo "$SA_PYTHON"; return; fi
  local r; r="$(pkg_dir)"
  if [ -x "$r/.venv/Scripts/python.exe" ]; then echo "$r/.venv/Scripts/python.exe"
  elif [ -x "$r/.venv/bin/python" ]; then echo "$r/.venv/bin/python"
  else echo "python"; fi
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