#!/usr/bin/env bash
# Verify a built wheel before installing it: no forbidden content, expected
# members, entry points present, and (when present) the SHA256SUMS entry.
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
py="$(resolve_python)"; wheel="$(wheel_path "${1:-}")"
require_python "$py" || exit 1
echo "Verifying: $wheel"
"$py" -m maintenance._release verify-wheel "$wheel"
# Cross-check against the committed checksum file when it has an entry.
sums="$(pkg_dir)/dist/SHA256SUMS"
if [ -f "$sums" ]; then
  expected="$(awk -v w="$(basename "$wheel")" '$2==w {print $1}' "$sums")"
  actual="$("$py" -c "import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" "$wheel")"
  if [ -n "$expected" ]; then
    [ "$expected" = "$actual" ] || { echo "ERROR: SHA256 mismatch for $(basename "$wheel")" >&2; exit 1; }
    echo "SHA256SUMS OK"
  else
    echo "note: no SHA256SUMS entry for $(basename "$wheel")"
  fi
fi