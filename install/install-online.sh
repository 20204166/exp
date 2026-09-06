#!/usr/bin/env bash
# Standalone online installer. It can be downloaded and run from any folder:
#   curl -fsSL https://raw.githubusercontent.com/20204166/exp/main/install/install-online.sh | bash
set -euo pipefail

base="https://raw.githubusercontent.com/20204166/exp/main/dist"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

download() {
  if command -v curl >/dev/null 2>&1; then curl -fsSL "$1" -o "$2"
  elif command -v wget >/dev/null 2>&1; then wget -qO "$2" "$1"
  else echo "curl or wget is required" >&2; exit 1; fi
}

choose_python() {
  local candidate version major minor
  for candidate in python3.13 python3.12 python3.11 python3.10 python3 python; do
    command -v "$candidate" >/dev/null 2>&1 || continue
    version="$($candidate -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || true)"
    [ -n "$version" ] || continue
    major="${version%%.*}"; minor="${version#*.}"
    if [ "$major" -gt 3 ] || { [ "$major" -eq 3 ] && [ "$minor" -ge 10 ]; }; then
      echo "$candidate"; return 0
    fi
  done
  echo "System Analyzer requires Python 3.10 or newer." >&2
  exit 1
}

py="$(choose_python)"
download "$base/SHA256SUMS" "$tmp/SHA256SUMS"
wheel="$(tail -n 1 "$tmp/SHA256SUMS" | tr -s ' ' | cut -d' ' -f2)"
[ -n "$wheel" ] || { echo "Could not determine the latest wheel" >&2; exit 1; }
download "$base/$wheel" "$tmp/$wheel"
expected="$(tail -n 1 "$tmp/SHA256SUMS" | cut -d' ' -f1)"
if command -v sha256sum >/dev/null 2>&1; then actual="$(sha256sum "$tmp/$wheel" | cut -d' ' -f1)"
elif command -v shasum >/dev/null 2>&1; then actual="$(shasum -a 256 "$tmp/$wheel" | cut -d' ' -f1)"
else actual="$("$py" -c 'import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$tmp/$wheel")"; fi
[ "$expected" = "$actual" ] || { echo "Wheel checksum mismatch" >&2; exit 1; }

install_pip() {
  local err; err="$(mktemp)"
  if "$@" --break-system-packages 2>"$err"; then rm -f "$err"; return 0; fi
  if grep -qi "no such option" "$err"; then rm -f "$err"; "$@"; return $?; fi
  cat "$err" >&2; rm -f "$err"; return 1
}

install_pip "$py" -m pip install --user "$tmp/$wheel"
bin_dir="$($py -c 'import sysconfig;print(sysconfig.get_path("scripts", scheme="posix_user"))')"
echo "Installed $wheel. Console scripts: $bin_dir"
if ! echo "$PATH" | tr ':' '\n' | grep -qx "$bin_dir"; then
  rc_file="$HOME/.profile"; case "$(basename "${SHELL:-bash}")" in
    zsh) rc_file="$HOME/.zshrc" ;; bash) rc_file="$HOME/.bashrc" ;; esac
  echo "Add it to PATH: echo 'export PATH=\"$bin_dir:\$PATH\"' >> $rc_file"
  echo "Then run: source $rc_file"
fi
echo "Run from anywhere: system-analyzer"
