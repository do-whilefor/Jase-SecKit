#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
require_linux
[[ $# -le 1 ]] || fail "Usage: bash scripts/build.sh [output]"
output=${1:-bin/pwnmesh}
tags=()
case ${PWNMESH_HEADLESS:-0} in
    0) build_web ;;
    1) tags=(-tags=headless) ;;
    *) fail "PWNMESH_HEADLESS must be 0 or 1." ;;
esac
mkdir -p -- "$(dirname -- "$output")"
node scripts/package-pi.mjs "$(dirname -- "$output")/runtime/pi"
CGO_ENABLED=0 go build -mod=readonly "${tags[@]}" -trimpath -ldflags='-s -w' -o "$output" ./cmd/pwnmesh
