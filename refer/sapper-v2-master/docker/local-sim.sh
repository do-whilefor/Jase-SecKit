#!/usr/bin/env bash
# local-sim.sh — full local-mode simulation of the TSecBench hosted run.
#
# Boots the mock platform (exact /openapi/v1/challenges contract) plus a
# vulnerable target on the HOST, then runs the sapper-agent container with
# --network host so the container reaches both. The container uses the REAL
# model gateway (Zhipu anthropic-compatible) and must autonomously:
#   list -> start -> solve via command injection -> capture 2 flags -> submit
#
# Usage: bash docker/local-sim.sh [image]     (default sapper-agent:kali)
set -uo pipefail
IMAGE="${1:-sapper-agent:kali}"
MOCK="${MOCK:-/tmp/mock_bench.py}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "== starting mock platform + vulnerable target ($MOCK) =="
python3 "$MOCK" > /tmp/mock_sim.log 2>&1 &
MOCK_PID=$!
trap 'kill $MOCK_PID 2>/dev/null' EXIT
sleep 2
PLATFORM=$(grep '^PLATFORM=' /tmp/mock_sim.log | cut -d= -f2)
TARGET=$(grep '^TARGET=' /tmp/mock_sim.log | cut -d= -f2 || true)
TARGET_M=$(grep '^TARGET_' /tmp/mock_sim.log | head -1 | cut -d= -f2 || true)
echo "platform=$PLATFORM target=${TARGET:-multi($TARGET_M)}"
[[ -n "$PLATFORM" ]] || { echo "mock failed to start"; cat /tmp/mock_sim.log; exit 1; }

echo "== running $IMAGE (real GLM engine, 12-minute budget) =="
docker run --rm --name sapper-sim --network host \
  -e BENCHMARK_BASE_URL="$PLATFORM" \
  -e BENCHMARK_TOKEN=mock-token \
  -e ANTHROPIC_BASE_URL="${ANTHROPIC_BASE_URL:-https://open.bigmodel.cn/api/anthropic}" \
  -e ANTHROPIC_AUTH_TOKEN="${ANTHROPIC_AUTH_TOKEN:?set ANTHROPIC_AUTH_TOKEN to the Zhipu key}" \
  -e SAPPER_MODEL="${SAPPER_MODEL:-glm-5.3-flash}" \
  -e SAPPER_TOTAL_MINUTES="${SAPPER_TOTAL_MINUTES:-12}" \
  -e SAPPER_MINUTES_PER_CHALLENGE="${SAPPER_MINUTES_PER_CHALLENGE:-6}" \
  "$IMAGE" 2>&1 | tee /tmp/sim-run.log

# report BEFORE the EXIT trap kills the mock platform; nested quotes in a
# single-quoted python -c broke every run — heredoc instead
echo "== platform-side state =="
curl -sS -m 10 "$PLATFORM/openapi/v1/challenges" -H "BENCHMARK_TOKEN: mock-token" \
  | python3 - <<'PYEOF'
import json, sys
try:
    items = json.load(sys.stdin)
except Exception:
    sys.exit(0)
for c in items:
    print(c.get("unique_code"),
          "%s/%s" % (c.get("correct_flag_count"), c.get("flag_count")),
          "COMPLETED" if c.get("is_completed") else "in-progress")
PYEOF
