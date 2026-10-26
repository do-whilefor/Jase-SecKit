#!/usr/bin/env bash
# oracle-miner.sh — Enumeration-oracle mining with a BUILT-IN negative control.
# Runs one request protocol against a positive identifier (claimed to exist),
# an auto-generated guaranteed-nonexistent identifier, and optional extra
# identifiers; captures status/size/time; diffs; prints a verdict.
#
# This is Core principle 2 mechanized: NO-ORACLE when positive == negative
# (the F25 PingFederate retraction rule). Never claim an enumeration oracle
# without this verdict.
#
# Usage:
#   ./oracle-miner.sh <url-template-with-IDENTIFIER> <positive-identifier> [options] [-- extra curl args...]
#     --neg-id ID        custom negative identifier (default: zzznonexistent<ts>@nowhere.com)
#     --field JSONPATH   also extract+diff one JSON field (python3; e.g. errors.0.message)
#     --rounds N         repeats per identifier, median taken (default 3, cap 5)
#
# Verdict:
#   ORACLE-DETECTED  positive differs from negative on status AND/OR size(>±20%) AND/OR time(>2x)
#   NO-ORACLE        identical responses — the "differential" was an artifact
#   WEAK-SIGNAL      differs on exactly one axis with small margin — re-test before claiming
#
# Scope = the targets the operator names.

set -uo pipefail
command -v curl >/dev/null 2>&1 || { echo "ERROR: 'curl' not found (Git Bash for Windows ships curl; check PATH)." >&2; exit 2; }
PYBIN=""
for _py in python3 python py; do
  command -v "$_py" >/dev/null 2>&1 && { PYBIN="$_py"; break; }
done
[[ -z "$PYBIN" ]] && { echo "ERROR: no python interpreter found (python3/python/py). Windows: python.org installer or 'winget install Python.Python.3'." >&2; exit 2; }
unset _py

[[ $# -lt 2 ]] && { grep -E "^#   (./oracle|\-\-)" "$0" | sed 's/^#   //'; exit 1; }
TEMPLATE="$1"; POSITIVE="$2"; shift 2
NEG_ID="zzznonexistent$(date +%s)@nowhere.com"; FIELD=""; ROUNDS=3
while [[ $# -gt 0 ]]; do
  case "$1" in
    --neg-id) NEG_ID="$2"; shift 2 ;;
    --field) FIELD="$2"; shift 2 ;;
    --rounds) ROUNDS="$2"; shift 2 ;;
    --) shift; break ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done
EXTRA_ARGS=("$@")
[[ $ROUNDS -gt 5 ]] && ROUNDS=5

run_rounds() { # $1=identifier → prints "status size time" (median of rounds)
  local id="$1" url hdr body st sz t
  local sts=() szs=() tms=()
  for ((i=1; i<=ROUNDS; i++)); do
    url="${TEMPLATE//IDENTIFIER/$id}"
    hdr=$(mktemp); body=$(mktemp)
    st=$(curl -s -o "$body" -D "$hdr" -w '%{http_code} %{time_total}' --max-time 20 \
         "${EXTRA_ARGS[@]}" "$url" 2>/dev/null)
    read -r st t <<< "$st"
    sz=$(wc -c < "$body")
    if [[ -n "$FIELD" ]]; then
      fv=$("$PYBIN" -c "
import json,sys
try:
    o=json.load(open(sys.argv[1],encoding='utf-8'))
    for k in sys.argv[2].split('.'):
        o=o[int(k)] if isinstance(o,list) else o[k]
    print(o)
except Exception:
    print('(none)')" "$body" "$FIELD" 2>/dev/null)
      echo "    [field $FIELD] = $fv"
    fi
    sts+=("$st"); szs+=("$sz"); tms+=("$t")
    rm -f "$hdr" "$body"
    sleep 0.4
  done
  echo "$(printf '%s\n' "${sts[@]}" | sort | head -1) $(printf '%s\n' "${szs[@]}" | sort -n | head -1) $("$PYBIN" -c "
import sys
v=[float(x) for x in sys.argv[1:]]
v.sort(); print(f'{v[len(v)//2]:.3f}')" "${tms[@]}")"
}

echo "=== oracle-miner ==="
echo "Template: $TEMPLATE"
echo "Positive: $POSITIVE    Negative: $NEG_ID    rounds=$ROUNDS"
echo ""
POS_OUT=$(run_rounds "$POSITIVE"); echo "positive → $POS_OUT  (status size time)"
NEG_OUT=$(run_rounds "$NEG_ID");  echo "negative → $NEG_OUT  (status size time)"
echo ""
read -r p_st p_sz p_tm <<< "$POS_OUT"
read -r n_st n_sz n_tm <<< "$NEG_OUT"
VERDICT="NO-ORACLE"; AXES=0
[[ "$p_st" != "$n_st" ]] && { AXES=$((AXES+1)); echo "axis: STATUS differs ($p_st vs $n_st)"; }
"$PYBIN" -c "
import sys
ps, ns, pt, nt = sys.argv[1:5]
dsz = abs(int(ps)-int(ns)) / max(int(ns), 1)
dtm = float(pt) / max(float(nt), 0.001)
sz = dsz > 0.20; tm = dtm > 2.0
print(f'axis: SIZE {\"differs\" if sz else \"same\"} ({ps}B vs {ns}B, {dsz*100:.0f}%)')
print(f'axis: TIME {\"differs\" if tm else \"same\"} ({pt}s vs {nt}s, {dtm:.1f}x)')
axes = (ps != ns) + sz + tm
# A >=3x same-status size ratio is decisive on its own — the F12 class
# (11740B vs 245B, both HTTP 200) must never be downgraded to a weak signal.
sz3 = int(ps) >= 3 * max(int(ns), 1) or int(ns) >= 3 * max(int(ps), 1)
if axes >= 2 or sz3: print('VERDICT: ORACLE-DETECTED — re-verify once more, then record as finding candidate.')
elif axes == 1: print('VERDICT: WEAK-SIGNAL — one axis only; raise rounds, add --field, re-test before claiming.')
else: print('VERDICT: NO-ORACLE — positive == negative. Do NOT claim an enumeration differential (F25 rule).')
" "$p_sz" "$n_sz" "$p_tm" "$n_tm"
