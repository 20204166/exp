#!/usr/bin/env bash
# Build the System Analyzer wheel into dist/. Building NEVER installs it.
# Offline: uses the already-present setuptools (no build isolation / no network).
#
# Before building, maintenance._release auto-bumps the package version when the
# source inputs differ from the newest built wheel, and syncs dist/SHA256SUMS
# afterwards. Override the bump with SA_VERSION_BUMP=none|patch|feature|minor.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$here/install/_common.sh"
py="$(resolve_python)"
bump="${SA_VERSION_BUMP:-auto}"

require_python "$py" || exit 1

cleanup() { rm -rf "$here/build" "$here"/*.egg-info; }
trap cleanup EXIT

echo "Preparing build inputs and version..."
"$py" -m maintenance._release prepare-build \
  --package-dir "$here" \
  --bump "$bump"

echo "Building system-analyzer wheel from: $here"
"$py" -m pip wheel "$here" --no-deps --no-build-isolation -w "$here/dist"

"$py" -m maintenance._release sync-artifacts --package-dir "$here"
echo "Built wheels:"
ls -1 "$here"/dist/system_analyzer-*.whl
echo "Building does not install. Run install.sh to install explicitly."