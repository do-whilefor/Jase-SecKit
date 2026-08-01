#!/usr/bin/env bash
# negative-control-harness.sh — Auto positive+negative control for any
# enumeration / differential claim. Sends the identical protocol against:
#   1. A user-provided "positive" identifier (claimed to exist)
#   2. A freshly-generated random identifier guaranteed not to exist
#   3. (Optional) Additional identifiers
#
# Then diffs status, size, and selected body fields. If positive == negative,
# YOU DO NOT HAVE AN ORACLE (see references/methodology-lessons.md Lesson 1).
#
# This is the harness that would have caught the F25 PingFederate false positive
# before submission.
#
# Usage:
#   ./negative-control-harness.sh <url-template> <positive-identifier> [curl-args...]
#
# The url-template must contain the literal string "IDENTIFIER" which gets
# substituted per request.
#
# Example (POST body with a JSON username):
#   ./negative-control-harness.sh \
#     "https://pentesting2.cdn.acmeauth.example/rp/fido/get" \
#     "admin@acmeauth.example" \
#     -X POST -H "Content-Type: application/json" \
#     -d '{"fidoPayload":{"context":{"transaction":"Reg","userName":"IDENTIFIER"},"op":"Reg","extras":{}},"session":{"sessionId":"x"}}'
#
# Authorized testing only.

set -uo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <url-or-template> <positive-identifier> [curl-args...]"
  echo "  The literal string IDENTIFIER in URL or any -d body is substituted per request."
  echo ""
  echo "Example:"
  echo "  $0 https://x.example.com/api/check admin@acmeauth.example -X POST -H 'Content-Type: application/json' \\"
  echo "     -d '{\"user\":\"IDENTIFIER\"}'"
  exit 1
fi

URL="$1"; shift
POSITIVE="$1"; shift

# Generate a guaranteed-nonexistent identifier
TS="$(date +%s)"
RAND="$(head -c 4 /dev/urandom | od -An -tx1 | tr -d ' \n')"
NEGATIVE="zzznonexistent${TS}${RAND}@nowhere.com"

OUTDIR="$(mktemp -d)"
trap 'rm -rf "$OUTDIR"' EXIT

echo "=== Negative Control Harness ==="
echo "Positive identifier: $POSITIVE"
echo "Negative identifier: $NEGATIVE (guaranteed nonexistent)"
echo "Output dir:          $OUTDIR"
echo ""

# Run the identical protocol against each identifier
run_one() {
  local label="$1"
  local ident="$2"
  shift 2
  # Substitute IDENTIFIER in URL and any -d '...' body argument
  local url_sub="${URL//IDENTIFIER/$ident}"
  local args=()
  for a in "$@"; do
    args+=("${a//IDENTIFIER/$ident}")
  done

  local body_file="${OUTDIR}/${label}.body"
  local headers_file="${OUTDIR}/${label}.headers"
  local stat=$(curl -s -o "$body_file" -D "$headers_file" -w "%{http_code} %{size_download} %{time_total}" "${args[@]}" "$url_sub")
  echo "$stat" > "${OUTDIR}/${label}.stat"
  echo "  [$label] ident=$ident"
  echo "          status/size/time: $stat"
  echo "          body sha256:      $(shasum -a 256 "$body_file" 2>/dev/null | awk '{print $1}')"
  echo "          body first 200B:  $(head -c 200 "$body_file" | tr -d '\n' | tr -d '\r')"
  echo ""
}

run_one "positive" "$POSITIVE" "$@"
run_one "negative" "$NEGATIVE" "$@"

# Diff
echo "=== Differential analysis ==="
POS_STAT=$(cat "${OUTDIR}/positive.stat")
NEG_STAT=$(cat "${OUTDIR}/negative.stat")
POS_BODY_SHA=$(shasum -a 256 "${OUTDIR}/positive.body" 2>/dev/null | awk '{print $1}')
NEG_BODY_SHA=$(shasum -a 256 "${OUTDIR}/negative.body" 2>/dev/null | awk '{print $1}')

if [[ "$POS_STAT" == "$NEG_STAT" && "$POS_BODY_SHA" == "$NEG_BODY_SHA" ]]; then
  echo "VERDICT: ⚠️  POSITIVE == NEGATIVE (status, size, time, AND body identical)"
  echo "         YOU DO NOT HAVE AN ORACLE."
  echo "         The differential you observed is likely:"
  echo "           - rate-limit counter state (per-source-IP)"
  echo "           - lockout cooldown (per-username)"
  echo "           - IP reputation"
  echo "           - some other transient condition unrelated to identifier existence"
  echo "         DO NOT submit this as an enumeration finding."
  echo "         See references/methodology-lessons.md Lesson 1 (F25 PingFederate retraction)."
  exit 2
fi

echo "Status: positive=$POS_STAT  negative=$NEG_STAT"
echo "Body:   positive_sha=$POS_BODY_SHA"
echo "        negative_sha=$NEG_BODY_SHA"
if [[ "$POS_BODY_SHA" != "$NEG_BODY_SHA" ]]; then
  echo ""
  echo "Full body diff:"
  diff <(cat "${OUTDIR}/positive.body") <(cat "${OUTDIR}/negative.body") | head -50
fi
echo ""
echo "VERDICT: ✅  Differential confirmed — but VERIFY the differential is due to"
echo "         identifier existence and NOT some other variable (e.g., rate-limit"
echo "         counter triggered by the positive request). If uncertain, run the"
echo "         harness multiple times with FRESH positive identifiers."
