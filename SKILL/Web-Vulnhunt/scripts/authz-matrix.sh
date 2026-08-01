#!/usr/bin/env bash
# authz-matrix.sh — Token × endpoint namespace matrix to find missing-@PreAuthorize
# authorization gaps. Sends the supplied token against every endpoint in an
# OpenAPI spec, buckets responses, and surfaces any 200-with-data that stands
# out against a class-wide pattern of 403.
#
# This is the methodology that found F5/F7/F9 — a single 200 among 78 properly-
# secured 403s in the IdP controller namespace.
#
# Usage:
#   ./authz-matrix.sh <base_url> <openapi-spec.json> <auth_header_value> [path_prefix]
#
# Example:
#   ./authz-matrix.sh https://tenant-001.cdn.acmeauth.example openapi-spec.json "hypwo-..." "/cc/api/"
#
# Requirements: python3, curl, jq
#
# Authorized testing only.

set -uo pipefail

if [[ $# -lt 3 ]]; then
  echo "Usage: $0 <base_url> <openapi-spec.json> <auth_header_value> [path_prefix]"
  echo ""
  echo "Example:"
  echo "  $0 https://tenant-001.cdn.acmeauth.example openapi-spec.json 'hypwo-...' '/cc/api/'"
  exit 1
fi

BASE_URL="${1%/}"; shift
SPEC="$1"; shift
TOKEN="$1"; shift
PREFIX="${1:-/}"

if [[ ! -f "$SPEC" ]]; then
  echo "Error: openapi spec not found: $SPEC"
  exit 1
fi

OUTDIR="$(mktemp -d)"
trap 'rm -rf "$OUTDIR"' EXIT
RESULTS="${OUTDIR}/results.tsv"
BODIES="${OUTDIR}/bodies"
mkdir -p "$BODIES"

echo "=== Authz Matrix ==="
echo "Base URL:    $BASE_URL"
echo "OpenAPI:     $SPEC"
echo "Token:       ${TOKEN:0:20}...(redacted)"
echo "Path prefix: $PREFIX"
echo ""

# Extract (method, path) pairs from OpenAPI spec, filtered by prefix.
# python+jq is more reliable across OpenAPI 3.x variants.
python3 - "$SPEC" "$PREFIX" <<'PY' > "${OUTDIR}/endpoints.tsv"
import json, sys
spec_path, prefix = sys.argv[1], sys.argv[2]
with open(spec_path) as f:
    spec = json.load(f)
for path, ops in spec.get("paths", {}).items():
    if not path.startswith(prefix):
        continue
    for method in ops:
        if method.lower() in ("get","post","put","patch","delete","head","options"):
            print(f"{method.upper()}\t{path}")
PY

TOTAL=$(wc -l < "${OUTDIR}/endpoints.tsv" | tr -d ' ')
echo "Endpoints to test: $TOTAL"
echo ""

# Build example bodies from OpenAPI requestBody schemas if available — minimal
# placeholder { } for now (manual schema-valid body crafting is documented in
# references/http-auth-filter-testing.md §1 as the follow-up step for any 400).
printf "%-6s %-8s %-8s %-10s %s\n" "METHOD" "STATUS" "SIZE" "VERDICT" "PATH"
printf "%-6s %-8s %-8s %-10s %s\n" "------" "------" "----" "-------" "----"

COUNT_200=0
COUNT_403=0
COUNT_401=0
COUNT_OTHER=0

while IFS=$'\t' read -r method path; do
  # Substitute {path-param} placeholders with ZZFAKE (per Lesson: use placeholder
  # for destructive endpoints, never real identifiers)
  url_path=$(echo "$path" | sed -E 's/\{[^}]+\}/ZZFAKE/g')
  url="${BASE_URL}${url_path}"

  body_file="${BODIES}/$(echo "${method}_${path}" | tr '/{}' '___').body"
  stat=$(curl -s -o "$body_file" -w "%{http_code} %{size_download}" \
    -X "$method" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{}' \
    "$url")
  code="${stat% *}"
  size="${stat#* }"

  verdict="?"
  case "$code" in
    200) verdict="DATA?"; COUNT_200=$((COUNT_200+1)) ;;
    403) verdict="secure"; COUNT_403=$((COUNT_403+1)) ;;
    401) verdict="authwall"; COUNT_401=$((COUNT_401+1)) ;;
    400) verdict="bad-body" ;;
    404) verdict="no-route" ;;
    405) verdict="method" ;;
    500) verdict="server-err" ;;
    *)   verdict="other"; COUNT_OTHER=$((COUNT_OTHER+1)) ;;
  esac

  printf "%-6s %-8s %-8s %-10s %s\n" "$method" "$code" "$size" "$verdict" "$path"
done < "${OUTDIR}/endpoints.tsv"

echo ""
echo "=== Summary ==="
echo "  200 (suspicious — investigate): $COUNT_200"
echo "  403 (properly secured):         $COUNT_403"
echo "  401 (auth wall):                $COUNT_401"
echo "  other:                          $COUNT_OTHER"
echo ""
echo "NEXT STEPS for any 200:"
echo "  1. Check the body in ${BODIES}/ — is it real data, or SPA HTML (SPA-FALLBACK)?"
echo "  2. If JSON data: look up the OpenAPI schema, craft a valid body, re-test."
echo "     If 200 persists with valid body → confirmed authorization gap."
echo "  3. Run the case-variant test (references/http-auth-filter-testing.md §1)"
echo "     to rule out SPA-FALLBACK masquerading as a controller hit."
echo ""
echo "Bodies saved in: $BODIES/"
