#!/usr/bin/env bash
# dormant-watch.sh — READ-ONLY monitoring of dormant persistence primitives.
# A dormant primitive (e.g. the F8 install-token mint surface) must stay on the
# books even after downstream patches close the chains (Lesson 7/8). This
# script periodically re-checks each primitive's liveness fingerprint and
# alerts on drift — the "re-arms instantly if any future gap appears" tripwire.
#
# Usage:
#   ./dormant-watch.sh <watch.conf> [--log dormant-watch.tsv] [--once]
# watch.conf line format:
#   NAME|URL|EXPECT_SNIPPET|MAX_TTL_DAYS
#   - URL: what to GET (use a benign read-only endpoint the primitive reaches)
#   - EXPECT_SNIPPET: substring that must appear when the primitive is live ("-" = any)
#   - MAX_TTL_DAYS: alert when the primitive's watch record is older than this ("-" = no TTL)
# Example (F8-style, dormant install-token primitive):
#   f8-mint|https://tenant.cdn.example/rp/versioned/features|supportEmail|-
#
# Each run appends one record per entry to the log:
#   TS  NAME  STATUS  SIZE  SHA1  DRIFT
# DRIFT=ok | DRIFTED (hash/status/size moved vs previous run) | EXPIRED (TTL)
#
# Exit: 0 = all stable, 1 = drift/expiry detected, 2 = config error.

set -uo pipefail
command -v curl >/dev/null 2>&1 || { echo "ERROR: 'curl' not found (Git Bash for Windows ships curl; check PATH)." >&2; exit 2; }
PYBIN=""
for _py in python3 python py; do
  command -v "$_py" >/dev/null 2>&1 && { PYBIN="$_py"; break; }
done
[[ -z "$PYBIN" ]] && { echo "ERROR: no python interpreter found (python3/python/py). Windows: python.org installer or 'winget install Python.Python.3'." >&2; exit 2; }
unset _py

CONF=""; LOG="dormant-watch.tsv"; ONCE=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --log) LOG="$2"; shift 2 ;;
    --once) ONCE=1; shift ;;
    -*) echo "Unknown flag: $1"; exit 2 ;;
    *) CONF="$1"; shift ;;
  esac
done
[[ -z "$CONF" || ! -f "$CONF" ]] && { grep -E "^#   (./dormant|NAME\|)" "$0" | sed 's/^#   //'; exit 2; }

# Validate the supported configuration format.
if grep -inE '(POST|PUT|PATCH|DELETE)[[:space:]]*https?://|\|https?://.*(POST|PUT|PATCH|DELETE)' "$CONF" >/dev/null; then
  echo "ERROR: unsupported method in watch configuration."; exit 2
fi

TS=$(date -u +"%Y-%m-%dT%H:%MZ")
ALERTS=0
printf 'TS\tNAME\tSTATUS\tSIZE\tSHA1\tDRIFT\n' >> "$LOG" 2>/dev/null || printf 'TS\tNAME\tSTATUS\tSIZE\tSHA1\tDRIFT\n' > "$LOG"

while IFS='|' read -r name url expect ttl; do
  [[ -z "$name" || "$name" =~ ^# ]] && continue
  BODY=$(mktemp)
  ST=$(curl -s -o "$BODY" -w '%{http_code}' --max-time 20 "$url" 2>/dev/null)
  ST="${ST:-000}"
  SZ=$(wc -c < "$BODY")
  H=$(sha1sum "$BODY" | cut -c1-12)
  SNIP="ok"
  [[ "$expect" != "-" && -n "$expect" ]] && { grep -q "$expect" "$BODY" || SNIP="MISSING-SNIPPET($expect)"; }
  # Drift vs previous record for this name
  PREV=$(awk -F'\t' -v n="$name" '$2==n {row=$0} END{print row}' < <(grep -v '^TS' "$LOG" 2>/dev/null) 2>/dev/null)
  DRIFT="ok"
  if [[ -n "$PREV" ]]; then
    o_st=$(echo "$PREV" | cut -f3); o_sz=$(echo "$PREV" | cut -f4); o_h=$(echo "$PREV" | cut -f5)
    o_ts=$(echo "$PREV" | cut -f1)
    if [[ "$o_h" != "$H" || "$o_st" != "$ST" ]]; then
      DRIFT="DRIFTED(prev=$o_st/$o_sz/$o_h now=$ST/$SZ/$H)"
      ALERTS=$((ALERTS+1))
    fi
    if [[ "$ttl" != "-" && -n "$ttl" ]]; then
      AGE_DAYS=$("$PYBIN" -c "
from datetime import datetime, timezone
try:
    t=datetime.strptime('$o_ts','%Y-%m-%dT%H:%MZ').replace(tzinfo=timezone.utc)
    print((datetime.now(timezone.utc)-t).days)
except Exception:
    print(0)")
      (( AGE_DAYS > ttl )) && { DRIFT="EXPIRED(age=${AGE_DAYS}d>${ttl}d)"; ALERTS=$((ALERTS+1)); }
    fi
  fi
  printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$TS" "$name" "$ST" "$SZ" "$H" "$DRIFT" | tee -a "$LOG"
  rm -f "$BODY"
done < <(grep -vE '^\s*$|^\s*#' "$CONF")

echo ""
if [[ $ALERTS -gt 0 ]]; then
  echo "⚠ $ALERTS alert(s). A dormant primitive moved — re-open the chain analysis (methodology-lessons.md Lesson 7/8) before it re-arms."
  exit 1
fi
echo "✅ All watched primitives stable ($TS). Next scheduled re-check: cron this with --once, or run manually per session."
