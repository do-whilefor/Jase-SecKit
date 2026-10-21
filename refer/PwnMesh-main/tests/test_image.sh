#!/bin/sh
# Run inside the application container started by scripts/test-docker.sh.
set -eu
pwnmesh --help >/dev/null
rg --version >/dev/null
health=$(curl --fail --silent --show-error --noproxy '*' \
    --retry 15 --retry-connrefused --retry-delay 1 --retry-max-time 15 --max-time 2 \
    http://127.0.0.1:8000/health)
printf '%s\n' "$health" | grep -Eq '"status"[[:space:]]*:[[:space:]]*"ok"'
curl --fail --silent --show-error --noproxy '*' \
    --max-time 2 http://127.0.0.1:8000/ >/dev/null
