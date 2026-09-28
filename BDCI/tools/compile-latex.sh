#!/usr/bin/env bash
# Tectonic interface: compile-latex.sh [tectonic options] document.tex
set -euo pipefail
tools_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export TECTONIC_CACHE_DIR="${TECTONIC_CACHE_DIR:-${tools_dir}/tectonic-cache}"
exec "${tools_dir}/bin/tectonic" "$@"
