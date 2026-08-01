#!/usr/bin/env bash
# sinkhole-detector.sh — Detect RFC 2544 DNS sinkhole (198.18.0.0/15) and
# recommend CT-log-only subdomain enumeration fallback.
#
# In the AcmeAuth engagement, Sessions 1-5 ran inside a network that returned
# 198.18.x.x sinkhole addresses for EVERY *.cdn.acmeauth.example / *.acmeauth.example query,
# including obviously-fabricated hostnames. This made DNS-based subdomain
# enumeration completely unreliable. The workaround was to pivot to CT-log-only
# enumeration and validate CT-discovered hostnames with live HTTP probing.
#
# Run this BEFORE trusting any DNS-based subdomain enum.
#
# Usage:
#   ./sinkhole-detector.sh <domain>
#
# Example:
#   ./sinkhole-detector.sh acmeauth.example

set -uo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <domain>"
  echo "Example: $0 acmeauth.example"
  exit 1
fi

DOMAIN="$1"
TS="$(date +%s)"
RAND="$(head -c 4 /dev/urandom | od -An -tx1 | tr -d ' \n')"
FAKE_HOST="totallymadeup${TS}${RAND}.${DOMAIN}"

echo "=== DNS Sinkhole Detector ==="
echo "Target domain: $DOMAIN"
echo "Probe host:    $FAKE_HOST (guaranteed nonexistent)"
echo ""

# Resolve the fake host — should be NXDOMAIN. If it returns anything (especially
# 198.18.x.x), we are behind a sinkhole.
RESOLVED=$(dig +short "$FAKE_HOST" 2>/dev/null | head -1)

if [[ -z "$RESOLVED" ]]; then
  echo "✅ CLEAN — fake host returned NXDOMAIN. DNS-based subdomain enumeration is reliable."
  echo ""
  echo "Recommended next step:"
  echo "  curl 'https://crt.sh/?q=%25.${DOMAIN}&output=json' | jq -r '.[].name_value' | sort -u"
  exit 0
fi

echo "⚠️  SUSPICIOUS — fake host resolved to: $RESOLVED"
echo ""

# Check if it's in the RFC 2544 benchmark range 198.18.0.0/15
if [[ "$RESOLVED" =~ ^198\.(1[89]|2[0-9]|3[01])\. ]]; then
  echo "🔴 SINKHOLE DETECTED — resolver returns RFC 2544 benchmark addresses (198.18.0.0/15)"
  echo "   for nonexistent hostnames. DNS-based subdomain enumeration will produce"
  echo "   false positives (every CT-discovered hostname will appear to 'resolve')."
  echo ""
  echo "WORKAROUND: pivot to CT-log-only enumeration + HTTP probe validation."
  echo ""
  echo "  Step 1: CT-log enumeration (no DNS)"
  echo "    curl 'https://crt.sh/?q=%25.${DOMAIN}&output=json' | jq -r '.[].name_value' | sort -u > ct-hosts.txt"
  echo ""
  echo "  Step 2: HTTP probe each CT-discovered host"
  echo "    while read h; do"
  echo "      code=\$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 5 \"https://\$h\")"
  echo "      if [[ \"\$code\" != \"000\" ]]; then"
  echo "        echo \"\$code  \$h\"  # real host"
  echo "      fi"
  echo "    done < ct-hosts.txt"
  echo ""
  echo "  Note: sinkhole IPs return 000/timeout on TCP connect. Real hosts return HTTP."
  echo "        In the AcmeAuth engagement: 190 CT-discovered hosts → 33 LIVE, 150 NXDOMAIN (decommissioned CT-only certs), 7 timeout/refused."
  exit 2
fi

echo "⚠️  AMBIGUOUS — fake host resolved to a non-RFC-2544 address."
echo "   This is unusual; investigate manually:"
echo "     dig $FAKE_HOST"
echo "     dig +trace $FAKE_HOST"
echo "   The resolver may be returning wildcard responses, captive-portal redirects,"
echo "   or search-domain appending."
echo ""
echo "  Validation step: also resolve a second distinct fake host and see if it"
echo "  resolves to the same IP (wildcard) or a different IP (suspicious)."
exit 3
