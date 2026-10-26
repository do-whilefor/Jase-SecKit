#!/usr/bin/env bash
# selftest.sh — Skill self-check. Validates the skill's own machinery without
# touching any network target: script syntax, reference wiring, the ledger
# round-trip, the JS toolchain on synthetic fixtures, and the corpus
# invariants (operator-scope model, hygiene language).
#
# Usage:
#   ./selftest.sh [-v]      # -v prints per-check command output
#
# Exit: 0 = all pass, 1 = failures (printed).
# Scope: n/a — this script only reads the skill directory and writes to a temp dir.

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
VERBOSE=0; [[ "${1:-}" == "-v" ]] && VERBOSE=1
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
PASS=0; FAIL=0; FAILED=()

check() { # $1=name $2=expected-ok(0/1) $3=command...
  local name="$1" expect="$2"; shift 2
  local out rc
  out=$("$@" 2>&1); rc=$?
  if [[ $rc == "$expect" ]]; then
    PASS=$((PASS+1)); echo "PASS  $name"
    [[ $VERBOSE == 1 ]] && { echo "$out" | sed 's/^/      /'; }
  else
    FAIL=$((FAIL+1)); FAILED+=("$name"); echo "FAIL  $name (rc=$rc, expected $expect)"
    echo "$out" | head -5 | sed 's/^/      /'
  fi
}

echo "=== selftest — $SKILL_DIR ==="
echo ""

# 1. Script inventory + syntax
echo "--- scripts ---"
for f in "$SCRIPT_DIR"/*.sh; do
  check "bash -n $(basename "$f")" 0 bash -n "$f"
done
for f in "$SCRIPT_DIR"/*.js; do
  check "node --check $(basename "$f")" 0 node --check "$f"
done
echo ""

# 2. Reference wiring: every file referenced from SKILL.md's table exists
echo "--- references ---"
while read -r ref; do
  check "exists references/$ref" 0 test -f "$SKILL_DIR/references/$ref"
done < <(grep -oE 'references/[a-z0-9-]+\.md' "$SKILL_DIR/SKILL.md" | sort -u | sed 's|references/||')
echo ""

# 3. Ledger round-trip
echo "--- ledger round-trip ---"
cd "$TMP"
check "ledger init" 0 "$SCRIPT_DIR/hunt-ledger.sh" init
check "ledger add (with falsification)" 0 "$SCRIPT_DIR/hunt-ledger.sh" add jwt "https://example.test" "alg=none accepted at /me" "re-sign without sig, expect 401"
check "ledger add REFUSED without falsification" 1 "$SCRIPT_DIR/hunt-ledger.sh" add jwt "https://example.test" "no falsification designed" "-"
check "ledger next shows hypothesis" 0 "$SCRIPT_DIR/hunt-ledger.sh" next
check "ledger update to killed" 0 "$SCRIPT_DIR/hunt-ledger.sh" update H-001 --status killed --result "401 as expected"
check "ledger list empty of open" 0 bash -c "\"$SCRIPT_DIR/hunt-ledger.sh\" list open | grep -q . && exit 1 || exit 0"
cd - >/dev/null
echo ""

# 4. JS toolchain on synthetic fixtures
echo "--- js toolchain ---"
SPEC="$TMP/mini-openapi.json"
cat > "$SPEC" <<'JSON'
{
  "openapi": "3.0.0",
  "paths": {
    "/api/redeem": {
      "post": {
        "requestBody": {
          "content": {
            "application/json": {
              "schema": {
                "type": "object",
                "required": ["code", "email"],
                "properties": {
                  "code": { "type": "string", "minLength": 6 },
                  "email": { "type": "string", "format": "email" },
                  "amount": { "type": "integer", "minimum": 1 }
                }
              }
            }
          }
        }
      }
    }
  }
}
JSON
node "$SCRIPT_DIR/valid-body-generator.js" "$SPEC" /api/redeem post --out "$TMP/valid-body.json" 2>/dev/null
check "valid-body-generator produces schema body" 0 node -e "
const b = JSON.parse(require('fs').readFileSync(process.argv[1], 'utf8'));
if (typeof b.code !== 'string' || b.code.length < 6) process.exit(1);
if (typeof b.email !== 'string' || !b.email.includes('@')) process.exit(1);
console.log('code/email present, format-valid');" "$TMP/valid-body.json"
check "valid-body-generator refuses undocumented method" 1 node "$SCRIPT_DIR/valid-body-generator.js" "$SPEC" /api/redeem delete

echo '{"provider":"acme","email":"admin@x.test"}' > "$TMP/sample-body.json"
check "body-mutator emits mutants" 0 node "$SCRIPT_DIR/body-mutator.js" "$TMP/sample-body.json" --out-dir "$TMP/mutants" --profiles proto-pollution,placeholder-swap
check "mutants manifest present" 0 test -f "$TMP/mutants/manifest.tsv"

cat > "$TMP/primitives.json" <<'JSON'
{"findings":[
 {"id":"F8","cvss":5.4,"outputs":["install-token","workstation-bearer"],"preconditions":[],"notes":"mint"},
 {"id":"F5","cvss":8.1,"outputs":["config-read"],"preconditions":["workstation-bearer"],"notes":"missing @PreAuthorize"},
 {"id":"F22","cvss":7.3,"outputs":["session-state"],"preconditions":["real-authenticator"],"notes":"blocked"}
]}
JSON
check "chain-matcher finds F8→F5" 0 bash -c "node \"$SCRIPT_DIR/chain-matcher.js\" \"$TMP/primitives.json\" | grep -q 'F8 → F5'"
check "chain-matcher honest boundary (F22 orphan)" 0 bash -c "node \"$SCRIPT_DIR/chain-matcher.js\" \"$TMP/primitives.json\" | grep -q 'F22: needs real-authenticator'"

echo '"/api/redeem","/api/settings"' > "$TMP/old.js"
echo '"/api/redeem","/api/settings","/api/admin/new-sink"' > "$TMP/new.js"
check "bundle-diff detects added endpoint" 0 bash -c "node \"$SCRIPT_DIR/bundle-diff.js\" \"$TMP/old.js\" \"$TMP/new.js\" | grep -q '/api/admin/new-sink'"
echo ""

# 5. Network scripts: usage/arg-validation paths only (no network)
echo "--- network scripts (usage paths) ---"
check "oracle-miner usage exit" 1 "$SCRIPT_DIR/oracle-miner.sh"
check "edge-mapper usage exit" 1 "$SCRIPT_DIR/edge-mapper.sh"
check "ratelimit-probe usage exit" 1 "$SCRIPT_DIR/ratelimit-probe.sh"
check "ratelimit-probe refuses cap>30" 1 "$SCRIPT_DIR/ratelimit-probe.sh" https://example.test --max 31
check "sweep-all usage exit" 1 "$SCRIPT_DIR/sweep-all.sh"
check "tenant-diff usage exit" 1 "$SCRIPT_DIR/tenant-diff.sh"
check "dormant-watch missing config exit 2" 2 "$SCRIPT_DIR/dormant-watch.sh" "$TMP/nonexistent.conf"
check "recon missing domain exit" 1 "$SCRIPT_DIR/recon.sh"
echo ""

# 6. Corpus invariants
echo "--- invariants ---"
check "operator-scope: no 'Authorized testing only' gate in scripts" 0 bash -c "grep -rln 'Authorized testing only' \"$SCRIPT_DIR\" | grep -v 'selftest.sh$' | grep -q . && exit 1 || exit 0"
check "operator-scope: no 'ask the user before' gate in live files" 0 bash -c "grep -rln 'ask the user before' \"$SKILL_DIR\" --include='*.md' --include='*.sh' --include='*.js' | grep -v 'review-log.md$' | grep -v 'selftest.sh$' | grep -q . && exit 1 || exit 0"
check "hygiene: negative-control rule present in SKILL.md" 0 grep -qi "negative control" "$SKILL_DIR/SKILL.md"
check "ethics §1 is the operator-scope model" 0 grep -q "The user's input is the authorization scope" "$SKILL_DIR/references/ethics-and-roe.md"
echo ""

echo "=== Summary: $PASS pass, $FAIL fail ==="
if [[ $FAIL -gt 0 ]]; then
  printf 'Failed: %s\n' "${FAILED[@]}"
  exit 1
fi
echo "All checks passed — the skill's machinery is internally consistent."
