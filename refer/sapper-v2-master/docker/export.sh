#!/usr/bin/env bash
# export.sh — save an image and keep only the two most recent tars.
# Usage: bash docker/export.sh [image] [out-tar]
#   default: sapper-agent:commander dist/sapper-agent-commander.tar.gz
# Rotation: <out>.prev2 deleted, .prev1 -> .prev2, current -> .prev1, then
# the fresh export becomes the current file. Disk never holds >2 versions.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="${1:-sapper-agent:commander}"
OUT="${2:-$REPO/dist/sapper-agent-commander.tar.gz}"

mkdir -p "$(dirname "$OUT")"
if [[ -f "$OUT.prev1" ]]; then mv -f "$OUT.prev1" "$OUT.prev2"; fi
if [[ -f "$OUT" ]]; then mv -f "$OUT" "$OUT.prev1"; fi

echo "==> exporting $IMAGE -> $OUT (keeping prev1/prev2 only)"
docker save "$IMAGE" | gzip -"${GZ_LEVEL:-1}" > "$OUT"
gzip -t "$OUT"
echo "==> done: $(du -h "$OUT" | cut -f1)  $(date +%H:%M:%S)"
