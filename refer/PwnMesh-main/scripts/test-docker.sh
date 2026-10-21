#!/usr/bin/env bash
# Verify the final image's default command in an isolated, disposable container.
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
[[ $# == 1 ]] || fail 'Usage: bash scripts/test-docker.sh IMAGE'
docker image inspect "$1" >/dev/null
container=$(docker create --pull never --network none "$1")
cleanup() {
    local status=$?
    if (( status != 0 )); then docker logs "$container" >&2 || true; fi
    docker rm -f -v "$container" >/dev/null
    exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
docker start "$container" >/dev/null
docker exec -i "$container" sh -s < "$PWNMESH_REPO_ROOT/tests/test_image.sh"
docker stop --time 10 "$container" >/dev/null
[[ $(docker inspect --format '{{.State.ExitCode}}' "$container") == 0 ]]
printf 'Application image checks passed\n'
