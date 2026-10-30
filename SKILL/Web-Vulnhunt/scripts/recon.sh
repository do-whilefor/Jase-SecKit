#!/usr/bin/env bash
# recon.sh — Asset recon for a fresh domain: sinkhole check → CT-log enumeration
# (jq-free) → vault-prefix mining → cloud error-leak pass → live-host validation.
# Produces the Phase-1 surface-map files that sweep-all.sh and the cold-start
# runbook consume. Read-only: DNS, HTTPS GETs to crt.sh and discovered hosts at
# paced rate.
#
# Usage:
#   ./recon.sh <domain> [--out DIR] [--delay-ms 500]
#
# Outputs in --out (default: recon-<domain>/):
#   hosts-all.txt hosts-live.txt vault-tenants.txt aws-accounts.txt surface-summary.txt
#

set -uo pipefail
command -v curl >/dev/null 2>&1 || { echo "ERROR: 'curl' not found (Git Bash for Windows ships curl; check PATH)." >&2; exit 2; }
PYBIN=""
for _py in python3 python py; do
  command -v "$_py" >/dev/null 2>&1 && { PYBIN="$_py"; break; }
done
[[ -z "$PYBIN" ]] && { echo "ERROR: no python interpreter found (python3/python/py). Windows: python.org installer or 'winget install Python.Python.3'." >&2; exit 2; }
unset _py

DOMAIN="${1:-}"; shift || true
[[ -z "$DOMAIN" ]] && { echo "Usage: $0 <domain> [--out DIR] [--delay-ms N]"; exit 1; }
OUT=""; DELAY_MS=500
while [[ $# -gt 0 ]]; do
  case "$1" in
    --out) OUT="$2"; shift 2 ;;
    --delay-ms) DELAY_MS="$2"; shift 2 ;;
    *) echo "Unknown flag: $1"; exit 1 ;;
  esac
done
OUT="${OUT:-recon-${DOMAIN}}"
mkdir -p "$OUT"
pacing() { sleep "$("$PYBIN" -c "print($DELAY_MS/1000)")"; }

echo "=== recon.sh — $DOMAIN → $OUT ==="

# 1. Sinkhole check (GATE G1)
FAKE="totallymadeup$RANDOM.$DOMAIN"
RESOLVED=$( (dig +short "$FAKE" 2>/dev/null || nslookup "$FAKE" 2>/dev/null | awk '/^Address/ {print $2}') | head -1)
SINKHOLED=0
if [[ -n "$RESOLVED" && "$RESOLVED" =~ ^198\.(1[89]|2[0-9]|3[01])\. ]]; then
  SINKHOLED=1
  echo "[G1] 🔴 SINKHOLE detected ($RESOLVED) → CT-log-only mode; DNS absence means nothing."
else
  echo "[G1] ✅ DNS clean → CT + DNS both usable."
fi

# 2. CT-log enumeration (primary; parsed with python — no jq dependency)
CT_OUT="$OUT/hosts-all.txt"
: > "$CT_OUT"
echo "[CT] crt.sh query for %.$DOMAIN ..."
curl -s --max-time 60 "https://crt.sh/?q=%25.${DOMAIN}&output=json" -o "$OUT/ct.json"
"$PYBIN" - "$OUT/ct.json" "$DOMAIN" >> "$CT_OUT" <<'PY' 2>/dev/null
import json, sys
try:
    rows = json.load(open(sys.argv[1], encoding="utf-8"))
except Exception:
    raise SystemExit
seen = set()
for r in rows:
    for n in r.get("name_value", "").split("\n"):
        n = n.strip().lstrip("*.").lower()
        if n and n.endswith(sys.argv[2]) and n not in seen:
            seen.add(n); print(n)
PY
sort -u "$CT_OUT" -o "$CT_OUT"
HOSTNAMES=$(wc -l < "$CT_OUT")
echo "[CT] $HOSTNAMES unique hostnames."

# 3. Vault-prefix mining (multi-tenant SaaS)
"$PYBIN" - "$CT_OUT" "$DOMAIN" > "$OUT/vault-tenants.txt" <<'PY'
import re, sys
pat = re.compile(rf"^vault-([^.]+)\.(\d{{12}})\.{re.escape(sys.argv[2])}$")
for line in open(sys.argv[1], encoding="utf-8"):
    m = pat.match(line.strip())
    if m:
        print(f"{m.group(1)}\t{m.group(2)}")
PY
VTS=$(wc -l < "$OUT/vault-tenants.txt")
echo "[VAULT] $VTS vault-<customer>.<aws-account> entries (tenant ownership candidates)."

# 4. Cloud error-leak pass (S3/CloudFront AccessDenied → STS ARN)
: > "$OUT/aws-accounts.txt"
for cand in "assets.$DOMAIN" "assets.dev.$DOMAIN" "cdn.$DOMAIN"; do
  pacing
  BODY=$(curl -sk --max-time 15 "https://$cand/" 2>/dev/null)
  ARNS=$(printf '%s' "$BODY" | grep -oE 'arn:aws:sts::[0-9]{12}:[^<"]+' | sort -u)
  if [[ -n "$ARNS" ]]; then
    echo "[CLOUD] $cand leaked STS ARNs:"; echo "$ARNS" | sed 's/^/    /'
    { echo "## $cand"; echo "$ARNS"; } >> "$OUT/aws-accounts.txt"
  fi
done

# 5. Live-host validation (skip when sinkholed? no — ALWAYS probe; sinkhole IPs fail TCP connect)
: > "$OUT/hosts-live.txt"
LIVE=0; PROBED=0
while IFS= read -r h; do
  [[ -z "$h" ]] && continue
  pacing; PROBED=$((PROBED+1))
  code=$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 5 --max-time 10 "https://$h" 2>/dev/null)
  [[ "$code" != "000" && -n "$code" ]] && { echo "$code $h" >> "$OUT/hosts-live.txt"; LIVE=$((LIVE+1)); }
done < "$CT_OUT"

# 6. Surface summary
{
  echo "# Surface summary — $DOMAIN  ($(date -u +%Y-%m-%dT%H:%MZ))"
  echo "sinkholed=$SINKHOLED  ct_hosts=$HOSTNAMES  live=$LIVE  probed=$PROBED  vault_entries=$VTS"
  echo "Live hosts: $(grep -c . "$OUT/hosts-live.txt" || true)  (see hosts-live.txt: '<status> <host>')"
  echo "Cloud leaks: $([[ -s "$OUT/aws-accounts.txt" ]] && echo YES || echo none)"
  echo ""
  echo "Next: ./sweep-all.sh <live-host> <openapi-spec.json>   (needs an API spec — mine docs/SPA bundle first)"
  echo "      Start the ledger:  ./hunt-ledger.sh init && ./hunt.sh status"
  echo "      Cold-start context: references/cold-start-runbook.md (GATE G2 = this file's output)"
} > "$OUT/surface-summary.txt"
cat "$OUT/surface-summary.txt"
