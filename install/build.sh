#!/usr/bin/env bash
# Build the System Analyzer wheel into dist/. Building NEVER installs it.
#
# Build-backend strategy: the offline fast path uses the setuptools already
# present in the resolved interpreter (--no-build-isolation, no network). When
# setuptools>=68 is missing there, build.sh falls back to pip build isolation,
# which installs the declared build requirement from the configured package
# source. Override with SA_BUILD_ISOLATION=auto|never|always. A failed build
# never leaves the package version bumped without a matching wheel.
#
# Before building, maintenance._release auto-bumps the package version when the
# source inputs differ from the newest built wheel, and syncs dist/SHA256SUMS
# afterwards. Override the bump with SA_VERSION_BUMP=none|patch|feature|minor.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$here/install/_common.sh"
py="$(resolve_python)"
bump="${SA_VERSION_BUMP:-auto}"
isolation="${SA_BUILD_ISOLATION:-auto}"

require_python "$py" || exit 1

cleanup() { rm -rf "$here/build" "$here"/*.egg-info; }
trap cleanup EXIT

# Detect the build backend BEFORE touching the version so a missing backend
# fails fast with a clear message instead of a pip traceback.
has_backend=0
if require_build_backend "$py" 2>/dev/null; then has_backend=1; fi

wheel_extra=()
case "$isolation" in
  never)
    if [ "$has_backend" -ne 1 ]; then
      echo "ERROR: build backend 'setuptools>=68' is not installed for $py." >&2
      echo "       Install it (e.g. '$py -m pip install \"setuptools>=68\"') or run" >&2
      echo "       with SA_BUILD_ISOLATION=auto|always to let pip fetch it." >&2
      exit 1
    fi
    wheel_extra=(--no-build-isolation)
    ;;
  always)
    wheel_extra=()
    ;;
  auto)
    if [ "$has_backend" -eq 1 ]; then
      wheel_extra=(--no-build-isolation)
    else
      echo "note: setuptools not found in $py; using pip build isolation to fetch the declared build requirement."
    fi
    ;;
  *)
    echo "ERROR: unknown SA_BUILD_ISOLATION='$isolation' (expected auto|never|always)" >&2
    exit 1
    ;;
esac

version_backup="$(mktemp)"
cp "$here/maintenance/_version.py" "$version_backup"
built_ok=0
restore_on_failure() {
  if [ "$built_ok" -ne 1 ]; then
    cp "$version_backup" "$here/maintenance/_version.py"
    echo "note: restored maintenance/_version.py after failed build" >&2
  fi
  rm -f "$version_backup"
}
trap 'cleanup; restore_on_failure' EXIT

echo "Preparing build inputs and version..."
"$py" -m maintenance._release prepare-build \
  --package-dir "$here" \
  --bump "$bump"

echo "Building system-analyzer wheel from: $here"
"$py" -m pip wheel "$here" --no-deps "${wheel_extra[@]}" -w "$here/dist"

"$py" -m maintenance._release sync-artifacts --package-dir "$here"
built_ok=1
echo "Built wheels:"
ls -1 "$here"/dist/system_analyzer-*.whl
echo "Building does not install. Run install.sh to install explicitly."