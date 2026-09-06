#!/usr/bin/env bash
# Upgrade to a given wheel, or build the latest wheel then install it.
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
py="$(resolve_python)"; echo "Before:"; show_version "$py"
if [ -n "${1:-}" ]; then
  wheel="$(wheel_path "$1")"
else
  bash "$(dirname "${BASH_SOURCE[0]}")/build.sh"
  wheel="$(wheel_path)"
fi
echo "Upgrading to: $(basename "$wheel")"
"$py" -m pip install --no-index --no-deps --force-reinstall "$wheel"
echo "After:"; show_version "$py"; echo "Rollback: rollback.sh <previous>"