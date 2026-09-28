#!/usr/bin/env bash
# Project-local compiler, pinned official release; no system TeX installation.
set -euo pipefail
bdci_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
archive="$(mktemp /tmp/bdci-tectonic.XXXXXX.tar.gz)"
trap 'rm -f "$archive"' EXIT
# The musl release fails TLS handshakes on this WSL host while GNU downloads
# the official bundle successfully. Keep musl explicit for non-glibc systems.
case "${TECTONIC_LINUX_VARIANT:-gnu}" in
  gnu) variant=gnu; digest=1a715688baf591e650c8aeb160ae934e181685eecbb38b317de30b269ac5d606 ;;
  musl) variant=musl; digest=8533d07f9ccbd7a65824b9e0459041bca34af1eb33daba48f59215593753a3b7 ;;
  *) echo 'TECTONIC_LINUX_VARIANT must be gnu or musl' >&2; exit 2 ;;
esac
url="https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%400.17.0/tectonic-0.17.0-x86_64-unknown-linux-${variant}.tar.gz"
curl --fail --location --retry 2 "$url" -o "$archive"
printf '%s  %s\n' "$digest" "$archive" | sha256sum --check -
mkdir -p "$bdci_dir/tools/bin" "$bdci_dir/tools/tectonic-cache"
tar -xzf "$archive" -C "$bdci_dir/tools/bin" tectonic
"$bdci_dir/tools/bin/tectonic" --version
