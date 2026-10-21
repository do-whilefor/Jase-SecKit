#!/usr/bin/env bash
# Check an existing Linux binary without building or downloading dependencies.
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
require_linux
[[ $# == 1 ]] || fail 'Usage: bash scripts/test.sh /absolute/path/to/pwnmesh'
[[ $1 == /* && -f $1 && -x $1 ]] || fail 'An absolute path to a Linux executable is required.'
clear_acceptance_env
clear_model_env
export PWNMESH_TEST_BINARY=$1
exec timeout 60 python3 -B tests/test_application.py
