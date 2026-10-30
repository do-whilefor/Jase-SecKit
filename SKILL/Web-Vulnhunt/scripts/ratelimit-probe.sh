#!/usr/bin/env bash
# ratelimit-probe.sh — Rate-limit characterization for one endpoint.
# Step-up schedule records response codes, delay, and limit headers.
#
# Usage:
#   ./ratelimit-probe.sh <url> [method] [--max N] [--curl-args ...]
#     --max N   request count (default 30)
#
# Records per request: index, delay, status, and any limit headers seen
# (X-RateLimit-*, Retry-After, 429). Verdict:
#   LIMITED@k    first 429/limit signal at request k (+ which header)
#   UNLIMITED    no limit signal within the sample (F24 pattern)
#

set -uo pipefail
[[ $# -lt 1 ]] && { grep -E "^#   (./ratelimit|\-\-)" "$0" | sed 's/^#   //'; exit 1; }
URL="$1"; shift
METHOD="GET"; MAX=30; EXTRA=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --max) MAX="$2"; shift 2 ;;
    GET|POST|PUT|DELETE|PATCH|HEAD) METHOD="$1"; shift ;;
    --) shift; EXTRA=("$@"); break ;;
    *) EXTRA+=("$1"); shift ;;
  esac
done
[[ $MAX -gt 30 ]] && { echo "ERROR: --max exceeds the supported value (30)."; exit 1; }

echo "=== ratelimit-probe ==="
echo "$METHOD $URL   cap=$MAX"
echo "idx  delay  status  limit-headers"
FIRST_429=0
# Step-up: 5 req @800ms, 5 @300ms, 5 @100ms, remainder @0ms.
for i in $(seq 1 "$MAX"); do
  if   (( i <= 5  )); then D=0.8
  elif (( i <= 10 )); then D=0.3
  elif (( i <= 15 )); then D=0.1
  else D=0; fi
  HDR=$(mktemp)
  ST=$(curl -s -o /dev/null -D "$HDR" -w '%{http_code}' --max-time 20 -X "$METHOD" "${EXTRA[@]}" "$URL" 2>/dev/null)
  LH=$(grep -iE '^(x-ratelimit|retry-after|rateLimit)' "$HDR" | tr -d '\r' | tr '\n' ';' | sed 's/;$//')
  printf '%3d  %4ss  %s  %s\n' "$i" "$D" "${ST:-000}" "${LH:--}"
  [[ "${ST:-}" == "429" && "$FIRST_429" == 0 ]] && FIRST_429=$i
  rm -f "$HDR"
  (( i < MAX )) && sleep "$D"
done
echo ""
if [[ "$FIRST_429" != 0 ]]; then
  echo "VERDICT: LIMITED — first 429 at request #$FIRST_429. Counting behavior characterized; factor into race/limit-overdraw hypotheses (references/race-conditions.md)."
else
  echo "VERDICT: UNLIMITED within the $MAX-request sample — a finding candidate (F24 pattern). Re-test with a fresh session/IP and record the negative control."
fi
